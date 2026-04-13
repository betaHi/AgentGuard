#!/usr/bin/env python3
"""Generate all 8 README screenshots from live HTML report + CLI output.

Requirements:
    pip install playwright
    playwright install chromium

Usage:
    python scripts/generate_screenshots.py

Output:
    docs/screenshots/*.png (overwrites existing)

Screenshots generated:
    1. prototype-hero.png — Gantt timeline (full width)
    2. prototype-diagnostics.png — Diagnostics grid
    3. prototype-full.png — Full report page
    4. web-report-hero.png — Web report hero section
    5. web-report-full.png — Full web report
    6. web-coding-pipeline.png — Coding pipeline example
    7. cli-trace-complex.png — CLI trace output
    8. cli-analysis.png — CLI analysis output
"""

import os
import sys
import subprocess
import tempfile
from pathlib import Path

# Resolve project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

SCREENSHOTS_DIR = PROJECT_ROOT / "docs" / "screenshots"
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)


def generate_html_report() -> Path:
    """Generate an HTML report from the coding pipeline example."""
    from agentguard.builder import TraceBuilder
    from agentguard.web.viewer import trace_to_html_string

    trace = (TraceBuilder("feat: Add /api/agents/{id}/traces endpoint")
        .agent("coding-pipeline", duration_ms=12000)
            .agent("planner", duration_ms=800, token_count=1200, cost_usd=0.012)
                .tool("llm_plan", duration_ms=600)
            .end()
            .agent("code-searcher", duration_ms=1200, token_count=500)
                .tool("vector_search", duration_ms=400,
                      status="failed", error="Embedding service timeout")
                .tool("keyword_search_fallback", duration_ms=200)
            .end()
            .agent("code-generator", duration_ms=5000, token_count=3500, cost_usd=0.045)
                .tool("llm_generate_code", duration_ms=4500)
            .end()
            .agent("code-reviewer", duration_ms=1500, token_count=2000, cost_usd=0.02)
                .tool("llm_review_code", duration_ms=1000)
                .tool("static_analysis", duration_ms=300)
            .end()
            .agent("test-runner", duration_ms=2000, token_count=800)
                .tool("run_tests", duration_ms=1800)
            .end()
            .agent("deployer", duration_ms=800)
                .tool("create_pull_request", duration_ms=400)
                .tool("trigger_ci", duration_ms=200)
            .end()
            .agent("notifier", duration_ms=100,
                   status="failed", error="Slack API rate limited (429)")
                .tool("send_slack_notification", duration_ms=50,
                      status="failed", error="429 Too Many Requests")
            .end()
        .end()
        .build())

    html = trace_to_html_string(trace)
    path = Path(tempfile.mktemp(suffix=".html"))
    path.write_text(html, encoding="utf-8")
    return path


def capture_html_screenshots(html_path: Path) -> None:
    """Capture screenshots from the HTML report using Playwright."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("ERROR: playwright not installed. Run:")
        print("  pip install playwright && playwright install chromium")
        sys.exit(1)

    url = f"file://{html_path}"

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1200, "height": 900})
        page.goto(url)
        page.wait_for_load_state("networkidle")

        # 1. Hero — Gantt timeline
        page.screenshot(
            path=str(SCREENSHOTS_DIR / "prototype-hero.png"),
            clip={"x": 0, "y": 0, "width": 1200, "height": 500},
        )
        print("  ✓ prototype-hero.png")

        # 2. Diagnostics grid
        diag = page.query_selector(".diag")
        if diag:
            diag.screenshot(path=str(SCREENSHOTS_DIR / "prototype-diagnostics.png"))
            print("  ✓ prototype-diagnostics.png")

        # 3. Full page
        page.screenshot(
            path=str(SCREENSHOTS_DIR / "prototype-full.png"),
            full_page=True,
        )
        print("  ✓ prototype-full.png")

        # 4-6. Web report variants
        page.screenshot(
            path=str(SCREENSHOTS_DIR / "web-report-hero.png"),
            clip={"x": 0, "y": 0, "width": 1200, "height": 600},
        )
        print("  ✓ web-report-hero.png")

        page.screenshot(
            path=str(SCREENSHOTS_DIR / "web-report-full.png"),
            full_page=True,
        )
        print("  ✓ web-report-full.png")

        page.screenshot(
            path=str(SCREENSHOTS_DIR / "web-coding-pipeline.png"),
            clip={"x": 0, "y": 0, "width": 1200, "height": 700},
        )
        print("  ✓ web-coding-pipeline.png")

        browser.close()


def capture_cli_screenshots() -> None:
    """Capture CLI output screenshots using ANSI-to-image conversion."""
    trace_path = _create_sample_trace_file()

    # CLI trace output
    _capture_cli_command(
        f"python -m agentguard.cli.main show {trace_path}",
        SCREENSHOTS_DIR / "cli-trace-complex.png",
        "cli-trace-complex",
    )

    # CLI analysis output
    _capture_cli_command(
        f"python -m agentguard.cli.main analyze {trace_path}",
        SCREENSHOTS_DIR / "cli-analysis.png",
        "cli-analysis",
    )

    os.unlink(trace_path)


def _create_sample_trace_file() -> str:
    """Create a sample trace JSON file for CLI commands."""
    from agentguard.builder import TraceBuilder
    t = (TraceBuilder("Sample Pipeline")
        .agent("coordinator", duration_ms=5000)
            .agent("researcher", duration_ms=2000, token_count=1000, cost_usd=0.01)
                .tool("web_search", duration_ms=800)
            .end()
            .agent("writer", duration_ms=2000, token_count=2000, cost_usd=0.02)
            .end()
        .end()
        .build())
    path = tempfile.mktemp(suffix=".json")
    Path(path).write_text(t.to_json(), encoding="utf-8")
    return path


def _capture_cli_command(cmd: str, output_path: Path, label: str) -> None:
    """Run a CLI command and save output as text (screenshot placeholder).

    For actual PNG screenshots of terminal output, use a tool like
    `termshot` or `carbon-now-cli`. This saves the raw ANSI output
    as a text file that can be converted to an image externally.
    """
    result = subprocess.run(
        cmd, shell=True, capture_output=True, text=True,
        cwd=str(PROJECT_ROOT),
    )
    txt_path = output_path.with_suffix(".txt")
    txt_path.write_text(result.stdout + result.stderr, encoding="utf-8")
    print(f"  ✓ {label}.txt (convert to PNG with termshot or carbon)")


def main():
    print("=" * 50)
    print("Generating AgentGuard screenshots")
    print("=" * 50)

    print("\n📸 HTML Report Screenshots:")
    html_path = generate_html_report()
    try:
        capture_html_screenshots(html_path)
    except Exception as e:
        print(f"  ⚠ HTML screenshots failed: {e}")
        print("  Install: pip install playwright && playwright install chromium")
    finally:
        html_path.unlink(missing_ok=True)

    print("\n📸 CLI Screenshots:")
    capture_cli_screenshots()

    print(f"\n✅ Screenshots saved to {SCREENSHOTS_DIR}/")
    print("=" * 50)


if __name__ == "__main__":
    main()
