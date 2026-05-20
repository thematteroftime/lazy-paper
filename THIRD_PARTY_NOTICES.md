# Third-Party Notices

lazy-paper includes code from the following projects.

## Onyx (formerly Danswer)

- **Source**: https://github.com/onyx-dot-app/onyx
- **Path vendored**: `backend/onyx/chat/citation_processor.py`
- **Local target**: `llm/citation/stream_processor.py`
- **Commit pinned**: `fa8fc678f9a8bc6d5e17a8810cef6ad426db1911`
- **License**: MIT

### Modifications

- Replaced imports of `onyx.configs.chat_configs.STOP_STREAM_PAT`, `onyx.context.search.models.SearchDoc`, `onyx.prompts.constants.TRIPLE_BACKTICK`, `onyx.server.query_and_chat.streaming_models.CitationInfo`, and `onyx.utils.logger.setup_logger` with the equivalent local types and stdlib `logging` in `llm/citation/models.py`.
- Added a file-level vendoring header.
- No logic changes; the streaming regex state machine and HYPERLINK / KEEP_MARKERS / REMOVE rendering modes are preserved verbatim.

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
