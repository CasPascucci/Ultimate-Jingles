# Cocoon Shell Jingles — Regex Rules

## Engine & matching behaviour

- Regex engine: **Kotlin/JVM** (`java.util.regex`), same as Java 8
- Matching is **case-insensitive** — never use `(?i)`, it is applied automatically
- Matching is **partial** (`containsMatchIn`) — a pattern does NOT need to cover
  the whole game title. `"zelda"` matches "The Legend of Zelda: Breath of the Wild"
- Patterns longer than 200 characters are silently skipped — keep them short
- Invalid regex silently falls back to substring matching, so typos won't break
  anything, but aim for valid patterns

## What Cocoon matches against

Cocoon matches the **scraped display title** of the game, not the raw filename.
Scraped titles look like "Luigi's Mansion" or "Fire Emblem: Awakening" — clean,
no region tags, no file extensions. This means:
- `^` and `$` anchors are safe and meaningful
- No-Intro filename abbreviations (e.g. `(USA)`, `.3ds`) are never present
- In-title abbreviations from the ROM community (mk7, nsmb2, albw) are also never
  present in scraped titles — include them only as a fallback for repos that might
  be used in other contexts

---

## Core pattern rules

### 1. Partial matching is the default — use `.*` as a wildcard gap

Separate title and subtitle with `.*`:
```
fire emblem.*awakening        ✓  (matches "Fire Emblem: Awakening")
fire emblem awakening         ✗  (fails if there's punctuation between them)
```

### 2. Make punctuation optional where scrapers may omit it

| Character | Treatment | Example |
|-----------|-----------|---------|
| Apostrophe `'` | `'?` | `luigi'?s mansion` |
| Period `.` | `\\.?` | `mario bros\\.? 2` |
| Exclamation `!` | `!?` | `hey!? pikmin` |
| Hyphen as word-joiner | `.?` | `fire.?emblem`, `yo.?kai`, `punch.?out` |

Use `.?` for hyphens that join compound words (Fire Emblem, Yo-Kai, Punch-Out)
because some scrapers output "FireEmblem", "YoKai", or "Punch Out" without the
hyphen. Do **not** use `.?` for hyphens that are purely subtitle separators
(those get replaced by `.*` per rule 1).

### 3. Roman numeral ↔ arabic number alternation

Always provide both forms for numbers in titles:

| Roman | Arabic | Pattern |
|-------|--------|---------|
| IV / iv | 4 | `(iv\|4)` |
| VI / vi | 6 | `(vi\|6)` |
| IX / ix | 9 | `(ix\|9)` |
| X / x  | 10 | `(x\|10)` |

**Caution**: Single-letter romans (`i`, `v`, `x`) are too short and will
match inside other words. Only apply them when they clearly stand alone as a
number (surrounded by spaces or end of string) and the game title makes it
unambiguous. When in doubt, omit the alternation — it is safer to miss an
edge case than to over-match.

### 4. Accent variants

Use character classes for accented letters that scrapers may or may not include:

```
pok[eé]mon    (matches "Pokemon" and "Pokémon")
```

Common ones: `[eé]`, `[eè]`, `[nñ]`, `[uü]`, `[oö]`

### 5. Use `^` and `$` anchors for short or generic titles

If the title is a single common word or very short phrase that would match
unrelated games, anchor it:

```
^fantasy life$       (prevents matching "Fantasy Life Online", etc.)
^luigi'?s mansion$   (prevents matching "Luigi's Mansion: Dark Moon")
^yo.?kai watch$      (prevents matching "Yo-Kai Watch 2", "Yo-Kai Watch 3")
```

Rule of thumb: anchor when the unanchored pattern would match a sequel or a
different game in the same series.

### 6. Use negative lookaheads to separate sequels and variants

When two titles share a prefix, use `(?!...)` on the shorter/earlier one:

```
super mario galaxy(?! 2)          (Galaxy yes, Galaxy 2 no)
pok[eé]mon sun$                   (Sun yes, Ultra Sun no — $ acts as lookahead)
pok[eé]mon moon$                  (Moon yes, Ultra Moon no)
final fantasy (x|10)(?![\\s-]*(2|ii))   (FFX yes, FFX-2 no)
new super mario bros\\.?.*wii(?!\\s*u)  (NSMB Wii yes, NSMB Wii U no)
```

The `$` anchor on Pokémon Sun/Moon works because "Pokémon Ultra Sun" does not
end with just "sun" — "ultra sun" is a longer suffix. Prefer `$` over lookaheads
when it does the same job with less complexity.

### 7. Alternate and regional titles

Where a game has a well-known alternate title (regional release name, common
fan abbreviation), add it as an `|` alternative:

```
rhythm heaven fever|beat the beat.*rhythm paradise
```

PAL / regional name examples to be aware of:
- *Rhythm Heaven Fever* (NA) = *Beat the Beat: Rhythm Paradise* (EU)
- *Final Fantasy VI* (SNES JP/EU) was released as *Final Fantasy III* (SNES NA)
- *NiGHTS: Journey of Dreams* — "NiGHTS" capitalisation is irrelevant since
  matching is case-insensitive; `nights.*journey of dreams` is sufficient

### 8. Abbreviations

Include common fan/community abbreviations as `|` alternatives. These won't
appear in scraped titles but are useful if the index is ever used against
raw filenames:

```
mario kart 7|mk7
mario kart wii|mkwii
new super mario bros\\.? 2|nsmb2
final fantasy (ix|9)|ffix|ff9
zelda.*a.?link between worlds|albw
majora'?s mask.*3d|mm3d
ocarina of time.*3d|oot3d
```

### 9. "The X" vs "X, The" title inversion

Scrapers may store "The Last Story" or "Last Story, The". Cover both:

```
the last story|last story
```

### 10. Series with multiple entries — be specific enough to distinguish them

When a series has multiple entries in the index, make sure no entry's pattern
matches another entry:

- Each Yo-Kai Watch entry must be distinct: anchor `^yo.?kai watch$` for the
  first game, and include the subtitle or number for the rest
- Each Mario & Luigi entry should include its subtitle keyword
- Each Pokémon game should be specific enough that Sun ≠ Ultra Sun, X ≠ XD, etc.

---

## Patterns to avoid

| Anti-pattern | Problem | Fix |
|---|---|---|
| `the demon blade` alone | Matches any game with that phrase | Always require `muramasa.*` before it |
| `journey of dreams` alone | Too generic | Always require `nights.*` before it |
| `last story` alone | Could match other games | Add `the last story\|last story` so both orderings are covered but the phrase stays specific |
| `pok[eé]mon x` unanchored | Matches "Pokémon XD: Gale of Darkness" | Use `pok[eé]mon x$` |
| `super mario galaxy` unanchored | Matches "Super Mario Galaxy 2" | Use `super mario galaxy(?! 2)` |
| Roman `x` as `(x\|10)` on "Pokémon X" | "x" is too ambiguous | Use `$` anchor instead: `pok[eé]mon x$` |

---

## Quick reference — Final Fantasy SNES edge case

The SNES US release of Final Fantasy VI was titled *Final Fantasy III* by Nintendo
of America. The No-Intro ROM name is `Final Fantasy III (USA)`. Scrapers may use
either name. Cover both:

```
final fantasy (vi|6|iii|3)(?!\\s*(advance|iv|4))|ff(vi|6)|ffiii(?!\\s*advance)
```

The lookahead blocks FFVI Advance (GBA) and the actual FFIII (NES) from matching.
