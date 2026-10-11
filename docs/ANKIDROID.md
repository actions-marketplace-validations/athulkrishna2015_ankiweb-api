# AnkiDroid integration APIs — ContentProvider, intents, JS bridge

> **Source:** [`ankidroid/Anki-Android`](https://github.com/ankidroid/Anki-Android)
> (`api/` module), the
> [AnkiDroid API wiki page](https://github.com/ankidroid/Anki-Android/wiki/AnkiDroid-API)
> and the [JavaScript API wiki page](https://github.com/ankidroid/Anki-Android/wiki/AnkiDroid-JavaScript-API),
> plus the [`ankidroid/apisample`](https://github.com/ankidroid/apisample) demo app.
> AnkiDroid is the official Anki client for Android; these APIs are **official**
> for the Android app, but they are Android-IPC surfaces — nothing here talks to
> ankiweb.net. For the network APIs see [SYNC.md](SYNC.md) and
> [ENDPOINTS.md](ENDPOINTS.md).

**Jump to:** [Surfaces](#api-surfaces) · [Setup](#client-setup-instant-add) ·
[Methods](#addcontentapi-methods) · [Provider URIs](#contentprovider-uri-map) ·
[Columns](#column-reference) · [Intents](#intent-api) ·
[JS API](#javascript-api) · [Testing](#testing-and-samples)

## API surfaces

AnkiDroid exposes three independent APIs:

| Surface                                    | Audience              | Transport                             | Use for                                            |
| ------------------------------------------ | --------------------- | ------------------------------------- | -------------------------------------------------- |
| **Instant-Add / ContentProvider** (`api/`) | other Android apps    | `content://com.ichi2.anki.flashcards` | Reading/writing notes, cards, decks, models, media |
| **Intents**                                | any Android app       | Android intents                       | Fallback sharing + triggering a sync               |
| **JavaScript API** (`AnkiDroidJS`)         | deck/template authors | WebView bridge inside the reviewer    | Custom card UIs calling native functions           |

A fourth path — bulk/low-level access — is just the raw ContentProvider with
your own queries; the Instant-Add library is the supported wrapper over it.

## Client setup (Instant-Add)

Gradle (JitPack), from the wiki:

```gradle
// root build.gradle
repositories { maven { url "https://jitpack.io" } }

// module build.gradle
dependencies {
    implementation 'com.github.ankidroid:Anki-Android:api-v1.1.0'
}
```

Required manifest entry on **Android 11+ (SDK 30)**, otherwise you get
`Failed to find provider info for com.ichi2.anki.flashcards`:

```xml
<manifest>
    ...
    <queries>
        <package android:name="com.ichi2.anki" />
    </queries>
</manifest>
```

Permissions and switches:

| Item                                                  | Value                                                                                                                    |
| ----------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| Permission (merged into your manifest by the library) | `com.ichi2.anki.permission.READ_WRITE_DATABASE`                                                                          |
| Runtime permission                                    | Enforced dynamically on Android M+; deny ⇒ fall back to the `ACTION_SEND` intent                                         |
| User toggle                                           | AnkiDroid → Settings → Advanced → **Enable AnkiDroid API** (off ⇒ provider unavailable)                                  |
| Availability check                                    | `AddContentApi.getAnkiDroidPackageName(context)` → package name or `null`                                                |
| Provider spec version                                 | `api.apiHostSpecVersion` → `1` (AnkiDroid 2.5: slow bulk ops, model-persist quirks) or `2` (2.6+); `-1` if not installed |
| Constants                                             | `AddContentApi.DEFAULT_DECK_ID = 1`, `AddContentApi.READ_WRITE_PERMISSION`                                               |

Minimal add (from the wiki; `addNotes()` is orders of magnitude faster than
looping `addNote()`):

```java
if (AddContentApi.getAnkiDroidPackageName(context) != null) {
    AddContentApi api = new AddContentApi(context);
    long deckId = api.addNewDeck("My app name");
    long modelId = api.addNewBasicModel("com.something.myapp");
    api.addNote(modelId, deckId, new String[] {"日の出", "sunrise"}, null);
} else {
    // fallback: ACTION_SEND share intent (see Intent API)
}
```

## AddContentApi methods

From [`api/src/main/java/com/ichi2/anki/api/AddContentApi.kt`](https://github.com/ankidroid/Anki-Android/blob/main/api/src/main/java/com/ichi2/anki/api/AddContentApi.kt):

| Method                                                                   | Returns                             | Purpose                                                                 |
| ------------------------------------------------------------------------ | ----------------------------------- | ----------------------------------------------------------------------- |
| `addNote(modelId, deckId, fields, tags)`                                 | `Long?`                             | Insert one note; cards land in `deckId`; no duplicate check             |
| `addNotes(modelId, deckId, fieldsList, tagsList)`                        | `Int`                               | Bulk insert (bulkInsert + `?deckId=` query param); returns count added  |
| `addMediaFromUri(fileUri, preferredName, mimeType)`                      | `String?`                           | Copy a file into `collection.media`; returns stored file name           |
| `findDuplicateNotes(mid, key)`                                           | `List<NoteInfo?>`                   | Duplicate lookup for one first-field key                                |
| `findDuplicateNotes(mid, keys)`                                          | `SparseArray<…>?`                   | Duplicate lookup for many keys (fast path on spec ≥ 2)                  |
| `getNoteCount(mid)`                                                      | `Int`                               | Note count for a model                                                  |
| `updateNoteTags(noteId, tags)`                                           | `Boolean`                           | Replace a note's tags; throws `SecurityException` if permission missing |
| `updateNoteFields(noteId, fields)`                                       | `Boolean`                           | Replace a note's fields                                                 |
| `getNote(noteId)`                                                        | `NoteInfo?`                         | Read id/fields/tags of one note                                         |
| `previewNewNote(mid, flds)`                                              | `Map<String, Map<String, String>>?` | Render a would-be note (requires full read-write permission)            |
| `addNewBasicModel(name)`                                                 | `Long?`                             | Create the standard two-field note type                                 |
| `addNewBasic2Model(name)`                                                | `Long?`                             | Create the "Basic (and reversed card)" note type                        |
| `addNewCustomModel(name, fields, cards, qfmt, afmt, css, did, sortf, …)` | `Long?`                             | Create a fully custom note type                                         |
| `getFieldList(modelId)`                                                  | `Array<String>?`                    | Field names of a model                                                  |
| `getModelList(minNumFields)`                                             | `Map<Long, String>?`                | Model id → name (filtered by field count)                               |
| `getModelName(mid)`                                                      | `String?`                           | Model name lookup                                                       |
| `addNewDeck(deckName)`                                                   | `Long?`                             | Create a deck; returns its id                                           |
| `setFlagRaw(noteId, rawFlag)`                                            | `Boolean`                           | Set flag by raw int on all of the note's cards                          |
| `setFlag(noteId, flag)`                                                  | `Boolean`                           | Same, using the `Flag` enum                                             |
| `selectedDeckName` _(property)_                                          | `String?`                           | Name of the currently selected deck                                     |
| `deckList` _(property)_                                                  | `Map<Long, String>?`                | All deck id → name pairs                                                |
| `getDeckName(did)`                                                       | `String?`                           | Deck name by id                                                         |
| `apiHostSpecVersion` _(property)_                                        | `Int`                               | Installed provider's spec version (`1`/`2`, `-1` absent)                |
| `getAnkiDroidPackageName(context)` _(static)_                            | `String?`                           | Package providing authority `com.ichi2.anki.flashcards`                 |

Supporting types (same package):

- **`NoteInfo`** — `getId()`, `getFields()`, `getTags()`, `getKey()` (first field).
- **`Flag`** — `NONE(0) RED(1) ORANGE(2) GREEN(3) BLUE(4) PINK(5) TURQUOISE(6) PURPLE(7)`.
- **`Ease`** — `EASE_1(1) … EASE_4(4)` (Again/Hard/Good/Easy).

## ContentProvider URI map

Authority: **`com.ichi2.anki.flashcards`** (constant `FlashCardsContract.AUTHORITY`),
base `content://com.ichi2.anki.flashcards`. The contract lives in
[`FlashCardsContract.kt`](https://github.com/ankidroid/Anki-Android/blob/main/api/src/main/java/com/ichi2/anki/FlashCardsContract.kt).

| URI                       | Supported     | Notes                                                                                                                              |
| ------------------------- | ------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| `/notes`                  | query, insert | Selection may use **libanki browser search syntax**; insert needs `mid`, `flds`, `tags` (+ `?deckId=` query param for bulk insert) |
| `/notes_v2`               | query         | Same rows, but selection is a **direct SQL WHERE** against the notes table                                                         |
| `/notes/<id>`             | query, update | Single note; append the id                                                                                                         |
| `/notes/<id>/cards`       | query         | All cards of the note as high-level rows (deck, question, answer)                                                                  |
| `/notes/<id>/cards/<ord>` | query, update | One card of the note (e.g. move it to another deck via `deck_id`)                                                                  |
| `/models`                 | query, insert | Note types; `/models/current` resolves the current model                                                                           |
| `/models/<id>`            | query         | One note type (field names, templates, css, counts)                                                                                |
| `/cards`                  | query         | All cards with scheduling columns (`Card.DEFAULT_COLUMNS`)                                                                         |
| `/schedule`               | query, update | ReviewInfo: next due cards & answering; selection `limit=?, deckID=?`                                                              |
| `/decks`                  | query, insert | All decks (`deck_name`, `deck_id`, counts, options…)                                                                               |
| `/selected_deck`          | query         | The deck last selected in the deck-chooser                                                                                         |
| `/media`                  | insert        | Copy a file into `collection.media` (`file_uri`, `preferred_name`)                                                                 |

MIME types follow `vnd.android.cursor.(dir|item)/vnd.com.ichi2.anki.(note|card|model)`.

## Column reference

### Note (`/notes`)

| Column                                       | Type   | Notes                                             |
| -------------------------------------------- | ------ | ------------------------------------------------- |
| `_id`                                        | long   | Note id (same as Anki's note id)                  |
| `guid`                                       | string | Stable unique id                                  |
| `mid`                                        | long   | Model (note type) id                              |
| `flds`                                       | string | Fields joined with `\x1f` (`Utils.joinFields`)    |
| `tags`                                       | string | Space-separated tag list                          |
| `sfld`                                       | string | Sort field                                        |
| `csum`                                       | long   | Checksum of the first field (duplicate detection) |
| `flags`, `data`, `mod`, `usn`, `allow_empty` | —      | Card flags, aux data, modification metadata       |

Insert with `ContentValues(mid, flds, tags)`; bulk insert honours the `deckId`
query parameter (`Note.DECK_ID_QUERY_PARAM`).

### Card (`/cards`)

| Column                                                                                               | Notes                              |
| ---------------------------------------------------------------------------------------------------- | ---------------------------------- |
| `_id`, `note_id`, `ord`, `card_name`, `deck_id`                                                      | Identity + template ordinal        |
| `question`, `answer`, `question_simple`, `answer_simple`, `answer_pure`                              | Rendered content (read-only views) |
| `reps`, `lapses`, `type`, `original_deck_id`                                                         | Counters and origin                |
| `queue`, `due`, `original_due`, `interval`, `sm2_factor`, `left`, `original_position`, `custom_data` | Raw scheduling                     |
| `fsrs_stability`, `fsrs_difficulty`, `fsrs_desired_retention`, `fsrs_decay`, `last_review_time_secs` | FSRS scheduler state               |
| `flags`                                                                                              | Flag colour (see `Flag` enum)      |

Default projection: `_id, note_id, ord, card_name, deck_id, question, answer, flags`.

### Model (`/models`)

`_id`, `name`, `field_names`, `num_cards`, `note_count`, `css`,
`sort_field_index`, `type`, `latex_pre`, `latex_post`, `deck_id`.
`CURRENT_MODEL_ID = "current"` addresses the current model.

### Deck (`/decks`, `/selected_deck`)

`deck_name`, `deck_id`, `deck_count`, `options`, `deck_dyn`, `deck_desc`.

### ReviewInfo (`/schedule`)

Read: `note_id`, `ord`, `button_count`, `next_review_times`, `media_files`.
Write (answer a card): `answer_ease` (1–4, see `Ease`), `time_taken`,
`bury`, `suspended`. Query selection: `limit=?, deckID=?`.

### Media (`/media`)

`file_uri` (source `Uri` of the file), `preferred_name` (name in
`collection.media`); insert returns the stored file's Uri.

## Intent API

Fallback / automation paths that need no permission and work on every
AnkiDroid version (from the [API wiki](https://github.com/ankidroid/Anki-Android/wiki/AnkiDroid-API)):

| Intent                                        | Details                                                                                                                                                                                                                           |
| --------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **`ACTION_SEND`** (recommended fallback)      | Type `text/plain`; **subject = front**, **text = back**. Build with `ShareCompat.IntentBuilder` so your app name is carried along. One card per send; the user completes the add in AnkiDroid.                                    |
| ~~`org.openintents.action.CREATE_FLASHCARD`~~ | **Deprecated since AnkiDroid 2.5.** Extras `SOURCE_TEXT` (front) and `TARGET_TEXT` (back). Kept for backwards compatibility only.                                                                                                 |
| **`com.ichi2.anki.DO_SYNC`**                  | Triggers a background sync (target type **Activity**). Throttled: a "server is busy" error appears if fired more often than once per 5 minutes. Works from Tasker/Automate; from a shell: `am start -a 'com.ichi2.anki.DO_SYNC'`. |

Share example:

```java
Intent shareIntent = ShareCompat.IntentBuilder.from(context)
        .setType("text/plain")
        .setSubject("日の出")     // front
        .setText("sunrise")       // back
        .getIntent();
if (shareIntent.resolveActivity(context.getPackageManager()) != null) {
    context.startActivity(shareIntent);
}
```

## JavaScript API

For deck/template authors: card templates can call native AnkiDroid functions
inside the reviewer's WebView via the injected `AnkiDroidJS` bridge.

### Setup and responses

```html
<script>
  // api version 0.0.3 with AnkiDroid 2.18 (0.0.2 with 2.17)
  var jsApiContract = { version: "0.0.3", developer: /* your email */ };
  var api = new AnkiDroidJS(jsApiContract);
  api.ankiGetCardDid().then(r => console.log(r)); // {success: true, value: '1707102058557'}
</script>
```

- Every call returns `Promise<{ success: boolean, value: any }>`.
- On failure: `success: false` plus a type-safe default in `value` —
  `false`, `-1`, `"unknown"`, `[]`, or `{}`.
- Failures are normal in the Previewer (e.g. `ankiGetETA()` is unavailable there).
- A `developer` contact **must** be provided; it is shown to users on breaking
  changes.

### Method list (AnkiDroid 2.18)

Enumerate at runtime with
`console.log(Object.keys(jsApiList).sort().join("\r\n"))`.

| Group              | Methods                                                                                                                                                                                                                                                                                                           |
| ------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Answering          | `ankiAnswerEase1..4`, `ankiShowAnswer`, `ankiIsDisplayingAnswer`                                                                                                                                                                                                                                                  |
| Bury / suspend     | `ankiBuryCard`, `ankiBuryNote`, `ankiSuspendCard`, `ankiSuspendNote`                                                                                                                                                                                                                                              |
| Mark / flag / tags | `ankiMarkCard`, `ankiToggleFlag` (`none/red/orange/green/blue`), `ankiAddTagToCard`, `ankiSetNoteTags(tags[])`                                                                                                                                                                                                    |
| Scheduling         | `ankiSetCardDue(days)`, `ankiResetProgress`, `ankiSearchCard`, `ankiSearchCardWithCallback`                                                                                                                                                                                                                       |
| Current card info  | `ankiGetCardId`, `ankiGetCardNid`, `ankiGetCardDid`, `ankiGetCardDue`, `ankiGetCardMod`, `ankiGetCardFactor`, `ankiGetCardFlag`, `ankiGetCardInterval`, `ankiGetCardLapses`, `ankiGetCardLeft`, `ankiGetCardMark`, `ankiGetCardODid`, `ankiGetCardODue`, `ankiGetCardQueue`, `ankiGetCardReps`, `ankiGetCardType` |
| Deck / counts      | `ankiGetDeckName`, `ankiGetNewCardCount`, `ankiGetLrnCardCount`, `ankiGetRevCardCount`, `ankiGetETA`, `ankiGetNextTime1..4`                                                                                                                                                                                       |
| UI state           | `ankiIsInFullscreen`, `ankiIsTopbarShown`, `ankiIsInNightMode`, `ankiIsActiveNetworkMetered`, `ankiEnableHorizontalScrollbar`, `ankiEnableVerticalScrollbar`                                                                                                                                                      |
| UI actions         | `ankiShowToast(msg)`, `ankiShowOptionsMenu`, `ankiShowNavigationDrawer`                                                                                                                                                                                                                                           |
| TTS / STT          | `ankiTtsSpeak`, `ankiTtsStop`, `ankiTtsSetLanguage`, `ankiTtsSetPitch`, `ankiTtsSetSpeechRate`, `ankiTtsIsSpeaking`, `ankiTtsFieldModifierIsAvailable`, `ankiSttStart`, `ankiSttStop`, `ankiSttSetLanguage`                                                                                                       |

Legacy **global functions** (no `api.` prefix) also work in templates:
`showAnswer()`, `buttonAnswerEase1()`…`buttonAnswerEase4()` (Again/Hard/Good/Easy),
`ankiShowToast(msg)`, `ankiShowOptionsMenu()`, `ankiShowNavDrawer()`.

A desktop-Anki port of most of this surface exists as the third-party
[AnkiJS-API](https://github.com/jhhr/AnkiJS-API) add-on (not part of either
org).

## Testing and samples

- **Sample app:** [`ankidroid/apisample`](https://github.com/ankidroid/apisample) —
  a Japanese→English dictionary prototype covering permission checks, duplicate
  checks, deck/model id persistence, tags and custom models. Its
  `AnkiDroid_Sync.prf.xml` is a ready-made Tasker profile for `DO_SYNC`.
- **Manual test checklist** (wiki): verify adds land in a deck named after your
  app; toggle _Enable AnkiDroid API_ off and confirm the intent fallback runs;
  on Android 6+ deny the runtime permission and confirm the fallback, then
  grant and confirm direct adds; uninstall AnkiDroid and confirm your app hides
  the option.
- **JS API test deck:** [ankiweb.net/shared/info/1045118423](https://ankiweb.net/shared/info/1045118423).
- Low-level provider implementation:
  [`AnkiDroid/src/main/java/com/ichi2/anki/provider`](https://github.com/ankidroid/Anki-Android/tree/main/AnkiDroid/src/main/java/com/ichi2/anki/provider).

---

Related pages: [SYNC.md](SYNC.md) — how AnkiDroid syncs over HTTP ·
[ENDPOINTS.md](ENDPOINTS.md) — the AnkiWeb `/svc/*` API ·
[ECOSYSTEM.md](ECOSYSTEM.md) — map of every Anki API surface.
