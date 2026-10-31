"""Entry: python3 -m konta2r"""
import sys


def main(argv=None):
    from konta2r.ui.app import main as ui_main
    return ui_main(argv)


if __name__ == "__main__":
    sys.exit(main())
