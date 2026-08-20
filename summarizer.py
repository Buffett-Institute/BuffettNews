"""
Uses the Claude API to write a short, punchy summary of an
article that also names its connection to the Roberta Buffett Institute.

Falls back to None (letting the caller use a simpler template) if no API
key is configured, the `anthropic` package isn't installed, or the call
fails for any reason -- the app should keep working without Claude access.
"""
try:
    import anthropic
except ImportError:
    anthropic = None

MODEL = "claude-opus-5"

SYSTEM_PROMPT = """You write short, eye-catching captions for the Roberta Buffett Institute for Global Affairs' news page at Northwestern University. 
Given an article's title, a gist of what it's about, and a note on how it connects to the Buffett Institute, 
write TWO punchy sentences (roughly 50 words) that:
- Captures what the article is actually about
- Names the specific Buffett Institute connection (a person's title/fellowship, a working group, a grant, a program, etc.) rather than gesturing at it vaguely
- Reads like a magazine caption, not a press release -- no throat-clearing like "This article discusses..."

Examples of the tone and level of specificity to match:
- "Northwestern scientists discovered animal signals share a universal tempo, research backed by Professor Daniel Abrams' Roberta Buffett Institute Global Collaboration Grant."
- "Buffett Faculty Fellow V.S. Subrahmanian and undergraduate researcher Isabel Gortner co-authored the first quantitative study of deepfake activity during the 2024 US presidential election."

Reply with only the two sentences -- no preamble, no quotation marks."""


def generate_short_description(title, article_gist, connection_note):
    """Returns a short AI-written summary, or None if Claude isn't available. 
    If the call fails, the summary will fall back on the simple summary which pulls whatever is on the webpage"""
    if anthropic is None or not connection_note:
        return None
    try:
        client = anthropic.Anthropic()
        user_content = (
            f"Article title: {title or '(unknown)'}\n"
            f"What the article covers: {article_gist or '(no summary available)'}\n"
            f"Its connection to the Buffett Institute: {connection_note}"
        )
        response = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            output_config={"effort": "low"},
            messages=[{"role": "user", "content": user_content}],
        )
        text = next((b.text for b in response.content if b.type == "text"), "")
        text = text.strip().strip('"')
        return text or None
    except Exception:
        return None