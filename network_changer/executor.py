from network_changer.errors import NetworkChangerException
from network_changer.interface import changer

import traceback
import argparse
import asyncio
import logging
import sys


commands = {}


class register:
    def __init__(self, name):
        self.name = name

    def __call__(self, kls):
        commands[self.name] = kls
        return kls


class Task:
    def run(self, argv=None):
        parser = argparse.ArgumentParser()
        parser.add_argument("--debug", action="store_true")
        parser = self.change_parser(parser) or parser
        args = parser.parse_args(argv)
        self.setup_logging(args)
        try:
            asyncio.run(self.execute_task(args))
        except:
            exc_info = sys.exc_info()
            print("#" * 80)
            for line in str(exc_info[1]).split("\n"):
                print(f"# {line}")
            if args.debug or not isinstance(exc_info[1], NetworkChangerException):
                print("!!")
                for line in "\n".join(traceback.format_tb(exc_info[2])).split("\n"):
                    print(f"!! {line}")

    @property
    def final_future(self):
        if not hasattr(self, "_final_future"):
            self._final_future = asyncio.get_event_loop().create_future()
        return self._final_future

    async def execute_task(self, args):
        raise NotImplementedError()

    def change_parser(self, parser):
        parser.add_argument("--interface", default=None, type=str)
        return parser

    def setup_logging(self, args):
        logging.basicConfig(
            format="%(asctime)-15s[%(levelname)s]:%(name)s: %(message)s", level=logging.INFO
        )


@register("info")
class Info(Task):
    async def execute_task(self, args):
        ch = changer(self.final_future, args.interface)
        for line in (await ch.info()).present():
            print(line)


@register("scan")
class Scan(Task):
    async def execute_task(self, args):
        ch = changer(self.final_future, args.interface)

        found = await ch.scan(progress={"debug": args.debug})
        for network in found:
            if args.filter_bssid and args.filter_bssid not in network.bssid:
                continue
            if args.filter_ssid and args.filter_ssid not in network.ssid:
                continue

            for line in network.present():
                print(line)
            print()

    def change_parser(self, parser):
        parser = super().change_parser(parser)
        parser.add_argument("--filter-bssid", default=None, type=str)
        parser.add_argument("--filter-ssid", default=None, type=str)
        return parser


@register("connect")
class Connect(Task):
    async def execute_task(self, args):
        ch = changer(self.final_future, args.interface)
        await ch.connect(args.ssid)
        print(f"Connected to {args.ssid}")

    def change_parser(self, parser):
        parser = super().change_parser(parser)
        parser.add_argument("--ssid", required=True, type=str)
        return parser


@register("disconnect")
class Disconnect(Task):
    async def execute_task(self, args):
        ch = changer(self.final_future, args.interface)
        await ch.disconnect()


def make_command_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=sorted(commands))
    return parser


def main(argv=None):
    parser = make_command_parser()
    args, argv = parser.parse_known_args(argv)
    return commands[args.command]().run(argv)


if __name__ == "__main__":
    main()
