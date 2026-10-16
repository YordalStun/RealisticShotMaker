"""python -m rsm  -> start the desktop app.   python -m rsm render shot.rsm.json -> render from the command line."""
import sys


def main():
    if len(sys.argv) > 1 and sys.argv[1] in ("render", "still", "job", "regrade"):
        from .cli import main as cli_main
        return cli_main(sys.argv[1:])
    from .gui.app import main as gui_main
    return gui_main()


if __name__ == "__main__":
    sys.exit(main())
