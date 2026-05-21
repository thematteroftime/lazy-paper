# Third-Party Notices

lazy-paper includes code from the following projects.

## Onyx (formerly Danswer)

- **Source**: https://github.com/onyx-dot-app/onyx
- **Original file referenced**: `backend/onyx/chat/citation_processor.py`
- **Local re-implementation**: `llm/citation/__init__.py::process_text`
- **License**: MIT

### Status

In v1.4.0–v1.7 the Onyx file was vendored verbatim at
`llm/citation/stream_processor.py` as a streaming
`DynamicCitationProcessor`. It was never wired into the runtime — the
adapter in `llm/citation/__init__.py` always took the non-streaming
`process_text` path. The vendored file was removed in v1.8.x; only the
three small support types it shared (`SearchDoc`, `CitationInfo`,
`STOP_STREAM_PAT`) remain in `llm/citation/models.py`.

The in-tree `process_text` retains the same three rendering modes
(HYPERLINK / KEEP / REMOVE) and the same span-marker grammar
(`[span:doc:start-end]`) as Onyx's design, but is non-streaming and
substantially shorter. This attribution preserves credit to Onyx for the
citation-processor design.

### MIT License (full text)

```
MIT License

Copyright (c) Onyx (formerly Danswer)

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
