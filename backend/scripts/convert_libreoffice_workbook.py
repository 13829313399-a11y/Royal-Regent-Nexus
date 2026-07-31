from __future__ import annotations

from argparse import ArgumentParser
from pathlib import Path
from time import monotonic, sleep

import uno


def _property(name: str, value):
    item = uno.createUnoStruct("com.sun.star.beans.PropertyValue")
    item.Name = name
    item.Value = value
    return item


def _connect(connection: str):
    local_context = uno.getComponentContext()
    resolver = local_context.ServiceManager.createInstanceWithContext(
        "com.sun.star.bridge.UnoUrlResolver",
        local_context,
    )
    deadline = monotonic() + 30
    while True:
        try:
            return resolver.resolve(connection)
        except Exception:
            if monotonic() >= deadline:
                raise
            sleep(0.25)


def main() -> None:
    parser = ArgumentParser()
    parser.add_argument("--connection", required=True)
    parser.add_argument("--mode", choices=("to-xlsx", "to-xls"), required=True)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--password", default="")
    args = parser.parse_args()

    context = _connect(args.connection)
    desktop = context.ServiceManager.createInstanceWithContext(
        "com.sun.star.frame.Desktop",
        context,
    )
    load_properties = (
        _property("Hidden", True),
        _property("ReadOnly", False),
        _property("MacroExecutionMode", 0),
        _property("UpdateDocMode", 0),
    )
    document = desktop.loadComponentFromURL(
        Path(args.input).resolve().as_uri(),
        "_blank",
        0,
        load_properties,
    )
    if document is None:
        raise RuntimeError("LibreOffice 无法打开源工作簿")

    try:
        filter_name = (
            "MS Excel 97"
            if args.mode == "to-xls"
            else "Calc MS Excel 2007 XML"
        )
        store_properties = [
            _property("FilterName", filter_name),
            _property("Overwrite", True),
        ]
        if args.password:
            store_properties.append(_property("Password", args.password))
        document.storeAsURL(
            Path(args.output).resolve().as_uri(),
            tuple(store_properties),
        )
    finally:
        document.close(True)


if __name__ == "__main__":
    main()
