import os.path
import typing

from mitmproxy import exceptions
from mitmproxy import flowfilter
from mitmproxy import io
from mitmproxy import ctx
from mitmproxy import flow


class Save:
    def __init__(self):
        self.stream = None
        self.filt = None
        self.active_flows = set()  # type: Set[flow.Flow]

    def open_file(self, path):
        if path.startswith("+"):
            path = path[1:]
            mode = "ab"
        else:
            mode = "wb"
        path = os.path.expanduser(path)
        return open(path, mode)

    def start_stream_to_path(self, path, flt):
        try:
            f = self.open_file(path)
        except IOError as v:
            raise exceptions.OptionsError(str(v))
        self.stream = io.FilteredFlowWriter(f, flt)
        self.active_flows = set()

    def configure(self, updated):
        # We're already streaming - stop the previous stream and restart
        if "save_stream_filter" in updated:
            if ctx.options.save_stream_filter:
                self.filt = flowfilter.parse(ctx.options.save_stream_filter)
                if not self.filt:
                    raise exceptions.OptionsError(
                        "Invalid filter specification: %s" % ctx.options.save_stream_filter
                    )
            else:
                self.filt = None
        if "save_stream_file" in updated:
            if self.stream:
                self.done()
            if ctx.options.save_stream_file:
                self.start_stream_to_path(ctx.options.save_stream_file, self.filt)

    def save(self, flows: typing.Sequence[flow.Flow], path: str) -> None:
        """
            Save flows to a file. If the path starts with a +, flows are
            appended to the file, otherwise it is over-written.
        """
        try:
            f = self.open_file(path)
        except IOError as v:
            raise exceptions.CommandError(v) from v
        stream = io.FlowWriter(f)
        for i in flows:
            stream.add(i)
        f.close()
        ctx.log.alert("Saved %s flows." % len(flows))

    def load(self, l):
        l.add_command("save.file", self.save)

    def tcp_start(self, flow):
        if self.stream:
            self.active_flows.add(flow)

    def tcp_end(self, flow):
        if self.stream:
            self.stream.add(flow)
            self.active_flows.discard(flow)

    def response(self, flow):
        if self.stream:
            self.stream.add(flow)
            self.active_flows.discard(flow)

    def request(self, flow):
        if self.stream:
            self.active_flows.add(flow)

    def done(self):
        if self.stream:
            for f in self.active_flows:
                self.stream.add(f)
            self.active_flows = set([])
            self.stream.fo.close()
            self.stream = None
