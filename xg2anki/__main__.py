"""Allow running xg2anki as a module: python -m xg2anki"""

from xg2anki.cli import main

if __name__ == '__main__':
    # Initialize colorama for Windows ANSI color support
    try:
        import colorama
        colorama.just_fix_windows_console()
    except ImportError:
        pass  # colorama not available, colors may not work on Windows

    main()
