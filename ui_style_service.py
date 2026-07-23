"""Load the static Streamlit stylesheet without importing Streamlit."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
STREAMLIT_CSS_RELATIVE_PATH = Path("assets") / "streamlit_app.css"


def load_streamlit_css(project_root: str | Path | None = None) -> str:
    root = PROJECT_ROOT if project_root is None else Path(project_root).resolve()
    css_path = root / STREAMLIT_CSS_RELATIVE_PATH
    try:
        css_text = css_path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise FileNotFoundError(
            f"Streamlit CSS file not found: {css_path}"
        ) from exc
    except UnicodeError as exc:
        raise RuntimeError(
            f"Unable to decode Streamlit CSS file as UTF-8: {css_path}"
        ) from exc
    except OSError as exc:
        raise OSError(
            f"Unable to read Streamlit CSS file: {css_path}: {exc}"
        ) from exc
    return f"\n<style>{css_text}</style>\n"
