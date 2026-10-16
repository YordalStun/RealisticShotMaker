"""python -m rsm  -> start the desktop app.   python -m rsm render shot.rsm.json -> render from the command line."""
import sys


def main():
    # a windowed (no console) build has no stdout; give print() somewhere to go
    import os
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w")
    if len(sys.argv) > 1 and sys.argv[1] in ("render", "still", "job", "regrade"):
        from .cli import main as cli_main
        return cli_main(sys.argv[1:])
    from .gui.app import main as gui_main
    return gui_main()


def run():
    try:
        return main()
    except SystemExit:
        raise
    except BaseException:
        # windowed builds have no console: keep a crash log the user can send
        import traceback
        from .blender_locator import app_data_dir
        log = app_data_dir() / "crash.log"
        log.write_text(traceback.format_exc(), encoding="utf-8")
        raise


if __name__ == "__main__":
    sys.exit(run())
