# deeptutor-book-lint

Offline structural linter for DeepTutor's on-disk `book_*` bundles — it tells you which field broke *before* the book silently disappears from the library.

DeepTutor saves every generated book as plain JSON, but validates it only inside the running API server. A bad field is caught by `Book.model_validate`, logged at WARNING, and replaced with `None`: the book vanishes and `/books/{id}/export` answers 404 with no hint about the cause. There is no CLI command to inspect the directory, and the on-disk layout is not in the storage docs. This tool reads that layout directly.

Upstream: https://github.com/HKUDS/DeepTutor

## What is missing upstream

- `deeptutor_cli/book.py` documents itself as maintenance-only: "Currently exposes maintenance commands. (Authoring/reading still goes through the API + web frontend.)" — [source](https://github.com/HKUDS/DeepTutor/blob/main/deeptutor_cli/book.py#L1-L5)
- `load_book()` swallows every validation error and returns `None` — [storage.py#L158-L170](https://github.com/HKUDS/DeepTutor/blob/main/deeptutor/book/storage.py#L158-L170)
- The official storage layout omits `data/user/workspace/book/` entirely — [DATA_STORAGE.md](https://github.com/HKUDS/DeepTutor/blob/main/docs-for-dev/DATA_STORAGE.md#L19-L31)
- The field contract exists only as Pydantic models (`deeptutor/book/models.py`); no JSON Schema is published.

So the failure mode is silent: you see a missing book, not a broken `page_ids` entry.

## What this tool does

Reads a `book_*` directory (or a parent directory of several) and checks, without importing DeepTutor and without network:

- `manifest.json` exists, parses, has an id, and uses a known `BookStatus`
- directory name matches `manifest.id`
- `spine.json` parses and its `book_id` matches the manifest
- chapter ids are unique, `content_type` is known
- every `chapter.page_ids` entry has a matching `pages/<id>.json`
- page `id` matches its filename, `book_id` matches the manifest, `chapter_id` exists in the spine
- pages are referenced by a chapter, page `order` is not duplicated
- block ids are unique, block `type`/`status` are known
- a `ready` block has a non-empty payload, and `quiz` / `flash_cards` / `timeline` / `section` / `code` / text blocks carry their required fields
- `page_count` / `chapter_count` agree with what is on disk (warning)

It does **not** generate, repair, or export books, and it does not talk to the API. Missing optional files (`progress.json`, `inputs.json`) are not errors.

## Install

No dependencies, Python 3.9+:

```bash
git clone git@github-linmoxi33:linmoxi33/deeptutor-book-lint.git
cd deeptutor-book-lint
./bin/deeptutor-book-lint examples/in/workspace
```

That command must print `1 book(s), 0 error(s), 0 warning(s)` and exit `0`.

## Usage

```bash
# one bundle
./bin/deeptutor-book-lint data/user/workspace/book/book_bk_demo

# every book_* under a workspace book directory
./bin/deeptutor-book-lint data/user/workspace/book

# CI: machine-readable, fail on errors
./bin/deeptutor-book-lint data/user/workspace/book --json

# fail on warnings too
./bin/deeptutor-book-lint data/user/workspace/book --strict
```

### `--json` output

```json
{
  "tool": "deeptutor-book-lint",
  "version": "0.1.0",
  "root": "examples/in/broken",
  "ok": false,
  "strict": false,
  "summary": { "books": 1, "errors": 7, "warnings": 2 },
  "books": [
    {
      "book_dir": "examples/in/broken/book_bk_bad",
      "book_id": "bk_bad",
      "title": "Broken Book",
      "status": "ready",
      "page_files": 1,
      "ok": false,
      "findings": [
        {
          "code": "SPN003",
          "severity": "error",
          "file": "spine.json",
          "path": "$.book_id",
          "message": "spine.book_id 'bk_other' != manifest.id 'bk_bad'"
        }
      ]
    }
  ]
}
```

The full checked-in snapshot is `examples/out/broken.json`.

### Exit codes

| Code | Meaning |
| --- | --- |
| `0` | no errors (warnings allowed unless `--strict`) |
| `1` | findings: errors, or warnings with `--strict` |
| `2` | usage or input error: path missing, no `book_*` bundle found, bad flag |

## Examples

```
examples/in/workspace/book_bk_demo/   valid two-page book  -> exit 0
examples/in/broken/book_bk_bad/       nine deliberate faults -> exit 1
examples/out/workspace.json           expected --json for the valid book
examples/out/broken.json              expected --json for the broken book
```

## Tests

```bash
python3 -m unittest discover -s tests -v
```

15 stdlib tests, no network, no fixtures outside `examples/`.

## Limits

- Validates the contract as of DeepTutor's `models.py` at the time of writing (2026-10-30); new enum values upstream will be reported as unknown until this list is updated.
- Structural only: it cannot tell whether prose is good, whether a citation resolves, or whether a quiz answer is correct.
- Reads JSON on disk; it does not repair files or call the API.
- A book with a missing `manifest.json` is reported as `BOOK001` (exit 1), not treated as absent.

## License

MIT
