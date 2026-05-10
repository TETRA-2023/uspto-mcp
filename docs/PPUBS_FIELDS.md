# PPUBS Field Catalogue

Reverse-engineered field reference for USPTO Patent Public Search at
`ppubs.uspto.gov`. **Locked 2026-05-10** against live probes of:

- `US-6103599-A` (USPAT, granted patent — fully populated)
- `US-20260126277-A1` (US-PGPUB, published application — many fields null pre-grant)

PPUBS has no public API documentation. Field counts and shapes below come
from inspecting actual response bodies, cross-referenced against
`riemannzeta/patent_mcp_server` (MIT, FastMCP). When PPUBS evolves, this
file moves with `src/server.py:RESPONSE_FIELDS` — the two **must** be
updated together.

For the wire protocol (auth, endpoints, request shapes) see
[`memory://main/tetra/uspto/uspto-ppubs-wire-protocol-locked-2026-05-10-against-live-probe`](https://docs.tetra-ai.fr) (BM project `main`).

## Endpoints surveyed

| Endpoint | Top-level keys | Per-record keys |
|---|---|---|
| `POST /api/searches/searchWithBeFamily` | 16 envelope keys | **89 per record** |
| `GET /api/patents/highlight/{guid}` | **450 fields** (flat) | n/a |
| `POST /api/searches/counts` | small flat shape | n/a |

## Tier rules

Every per-record field in PPUBS responses lands in one of three tiers
defined by `RESPONSE_FIELDS` in `src/server.py`. Verbosity-aware tools
(`ppubs_search_patents`, `ppubs_get_patent_by_number`) accept
`verbosity="minimal"|"standard"|"full"` and filter accordingly.

| Tier | Goal | Search-record count | Detail-record count |
|---|---|---|---|
| `minimal` | Disambiguating ID line; fits one display row | 6 | 8 |
| `standard` | Patent-attorney triage view | 18 | 37 |
| `full` | No filter — raw payload | 89 | 450 |

**Standard-tier exclusion principles**:

- KWIC noise (`*KwicHits`, `*Highlights` suffixes) — search-side highlight metadata, never useful programmatically
- `pf*` preferred-publication duplicates of cleaner canonical fields
- Long-form classification arrays when `*Flattened` says it concisely
- Image / Solr internals (`compositeId`, `documentId*`, `objectId`, `urpn*`, `score` only kept on summary)
- Derwent third-party indexing (`derwent*`, `*Derwent`, `cpiManualCodes`, etc.)
- PCT/Hague/foreign-citation/sequence/biological/polymer metadata (niche, full-only)

---

## Search-response per-record fields (89 total)

Returned by `POST /api/searches/searchWithBeFamily` inside `patents[]`.

### IDs and disambiguation (10 fields)

| Field | Tier | Notes |
|---|---|---|
| `guid` | minimal | Primary identifier — e.g. `"US-20260126277-A1"`. Required for `/highlight/` lookup. |
| `type` | minimal | `"US-PGPUB"`, `"USPAT"`, or `"USOCR"`. Maps to the `source` query param on detail fetch. |
| `kindCode` | minimal | List, e.g. `["A"]` (older grant), `["A1"]`/`["A2"]` (PGPUB), `["B1"]`/`["B2"]` (post-2001 grant), `["E"]` (reissue). |
| `source` | full | Solr-internal — duplicates `type`. |
| `databaseName` | full | Solr-internal collection name. |
| `compositeId` | full | Solr partition + doc ID. |
| `documentId`, `documentIdWithDashesDw` | full | Internal IDs. |
| `urpn`, `urpnCode` | full | Search-internal patent number ref. |

### Title and pub#/app# (6 fields)

| Field | Tier | Notes |
|---|---|---|
| `inventionTitle` | minimal | The title. **Not** `"title"`. |
| `publicationReferenceDocumentNumber` | minimal | Canonical pub#. |
| `publicationReferenceDocumentNumber1`, `publicationReferenceDocumentNumberOne` | full | Two redundant variants. |
| `applicationNumber` | standard | E.g. `"18/932154"`. |
| `cpcCodes` | full | Raw CPC list — `cpcInventiveFlattened` says it concisely. |

### Dates (8 fields)

| Field | Tier | Notes |
|---|---|---|
| `datePublished` | minimal | ISO datetime. |
| `applicationFilingDate` | standard | List — multiple values for continuation chains. |
| `priorityClaimsDate` | full | Priority date if separate. |
| `relatedApplFilingDate` | full | Continuity chain. |
| `pfApplicationDate`, `pfPublDate` | full | Preferred-* duplicates. |
| `*KwicHits` (×2 here) | full | KWIC noise. |

### People (3 fields, search-side only)

| Field | Tier | Notes |
|---|---|---|
| `inventorsShort` | standard | Compact `"Doe; Jane et al."` Often empty for US-PGPUB. |
| `applicantName` | standard | List. Always populated where there's an applicant. |
| `assigneeName` | standard | List. Empty pre-grant on US-PGPUB. |

### Classification (5 fields, flattened only)

| Field | Tier | Notes |
|---|---|---|
| `mainClassificationCode` | standard | Legacy USPC primary class. |
| `ipcCodeFlattened` | standard | IPC slash-joined. |
| `cpcInventiveFlattened` | standard | CPC inventive, semicolon-joined. |
| `cpcAdditionalFlattened` | standard | CPC additional. |
| `uspcFullClassificationFlattened` | full | Full USPC including subclasses. |

### Family (5 fields)

| Field | Tier | Notes |
|---|---|---|
| `familyIdentifierCur` | standard | INPADOC-style family ID. Int. |
| `familyIdentifierCurStr` | full | String form. |
| `patentFamilyCountry`, `patentFamilyMembers`, `patentFamilySerialNumber` | full | Family member detail. |

### Examiners (2 fields)

| Field | Tier | Notes |
|---|---|---|
| `primaryExaminer` | standard | Often null on US-PGPUB; populates at examination. |
| `assistantExaminer` | full | Often null. |

### Page-range pointers (28 fields)

14 `*Start`/`*End` pairs for PDF assembly. None in standard tier — patent attorneys don't paginate PDFs through the MCP. Pairs:

`abstract`, `amend`, `bib`, `certCorrection`, `certReexamination`, `claims`, `description`, `drawings`, `frontPage`, `ptab`, `searchReport`, `specification`, `supplemental`, plus an outlier `pageCount`/`pageCountDisplay`.

### Solr/internal noise (10 fields)

`queryId`, `score`, `tags`, `unused`, `previouslyViewed`, `clippedUri`, `languageIndicator`, `governmentInterest`, plus the 4 `dwImage*`/`dwPage*` lists and `imageFileName`/`imageLocation`. Standard surfaces only `score` (search relevance ranking).

### KWIC highlights (5 fields)

`applicationFilingDateKwicHits`, `datePublishedKwicHits`, `pfApplicationDateKwicHits`, `pfPublDateKwicHits`, `priorityClaimsDateKwicHits` — keyword-in-context match data. Never standard.

### `pf*` preferred-* duplicates (5 fields)

`pfApplicationDate`, `pfApplicationDescriptor`, `pfApplicationSerialNumber`, `pfLanguage`, `pfPublDate` — duplicates of canonical fields, with the highest-priority family member's value. Surface only at full.

### Other (2 fields)

`derwentAccessionNumber` (full only — third-party indexing), `documentSize` (full only — int byte count).

---

## Detail-response fields (450 total)

Returned by `GET /api/patents/highlight/{guid}?source=<type>&queryId=1&includeSections=true`. Top-level flat dict.

The detail response is the search response **plus** all the
classification/people/citation/family detail that PPUBS holds. Below are
the ~15 categories. Tier annotations apply when the field is included in
that tier; otherwise it lives in `full` only.

### Inventors (13 fields)

`inventorsName` **(standard)** — list of full names per inventor.
`inventorsShort` **(minimal)** — compact display string.
`inventors` (full — structured group).
`inventorCity` / `inventorState` / `inventorCountry` / `inventorPostalCode` / `inventorStreetAddress` / `inventorText` (full — parallel arrays, indexed alongside `inventorsName`).
`inventorCitizenship` / `inventorDeceased` / `inventorNameDerived` / `inventorCorrection` (full — per-inventor metadata).

### Applicants (8 fields)

`applicantName` **(standard)** — list.
Address: `applicantCity`, `applicantState`, `applicantCountry`, `applicantZipCode` (full — parallel arrays).
Group: `applicantAuthorityType`, `applicantDescriptiveText`, `applicantGroup`, `applicantHeader` (full).

### Assignees (8 fields)

`assigneeName` **(standard)** — list.
Address (standard): `assigneeCity`, `assigneeState`, `assigneeCountry`.
Other: `assignee1`, `assigneePostalCode`, `assigneeDescriptiveText`, `assigneeTypeCode` (full).

### Legal/correspondence (10 fields)

`legalFirmName` **(standard)** — list. Typically populated; `attorneyName` often null.
`attorneyName`, `principalAttorneyName`, `associateAttorneyName` (standard, often null but cheap).
Legal rep address (full): `legalRepresentativeName`/`City`/`State`/`Country`/`Postcode`/`StreetAddress`/`Text`.
`correspondenceAddressCustomerNumber`, `correspondenceNameAddress`, `customerNumber` (full).

### Examiners (5 fields)

`primaryExaminer` **(standard)**, `assistantExaminer` **(standard)** — both surface (assistant often null).
`examinerGroup`, `examinerGroupHtml`, `primaryExaminerHighlights` (full — KWIC highlights of primary).

### CPC classification (~20 fields)

Standard only carries the two flattened forms: `cpcInventiveFlattened`, `cpcAdditionalFlattened`.

Full carries: `cpcInventive`, `cpcAdditional`, `cpcAdditionalLong`, `cpcCodes`, `cpcCisClassificationOrig`, `cpcCombinationClassificationCur`, `cpcCombinationClassificationOrig`, `cpcCombinationSetsCurHighlights`, `cpcCombinationTallyCur`, `cpcCurAdditionalClass`, `cpcCurAdditionalClassification`, `cpcCurClassificationGroup`, `cpcCurInventiveClass`, `cpcOrigAdditionalClassification`, `cpcOrigClassificationGroup`, `cpcOrigInventiveClassificationHighlights`, `curCpcClassificationFull`, `curCpcSubclassFull`, `issuedCpcClassificationFull`, plus 4 `cpc*KwicHits` variants.

### IPC classification (~25 fields)

Standard only carries `ipcCodeFlattened`.

Full carries: `ipcCode`, `ipcAllMainClassification`, the 7-field `internationalClassification*` group, the 11-field `intlPubClassification*`/`curIntlPatentClassification*` groups (current + various date variants), `intlFurtherClassification`, `issuedIpcClassificationFull`, plus KWIC variants.

### USPC classification (legacy, ~10 fields)

Standard only carries `mainClassificationCode`.

Full carries: `uspcCodeFmtFlattened`, `uspcFullClassification`, `uspcFullClassificationFlattened`, `usClassIssued`, `curUsClassificationUsPrimaryClass`, `curUsClassificationUsSecondaryClass`, `currentUsCrossReferenceClassification`, `currentUsOriginalClassification`, `currentUsOriginalClassificationLong`, `currentUsPatentClass`, `issuedUsClassificationFull`, `issuedUsCrossRefClassification`, `issuedUsDigestRefClassifi*` (typo on USPTO side — both forms exist), `issuedUsOrigClassification`.

### Foreign classification (~10 fields)

`europeanClassification` + 2 variants (full).
`jpoFiClassification`, `jpoFiCurrentAdditionalClassification`, `jpoFiCurrentInventiveClassification`, `jpoFtermCurrent` (full — JPO File Index).
`locarnoClassification`, `locarnoMainClassification` (full — design patents).

### Field-of-search classification (7 fields)

`fieldOfSearchCpcClassification`, `fieldOfSearchCpcMainClass`, `fieldOfSearchIpcMainClass`, `fieldOfSearchIpcMainClassSubclass`, `fieldOfSearchMainClassNational`, `fieldOfSearchSubclasses`, `fieldOfSearchClassSubclassHighlights` (all full).

### Heavy text (15 fields)

Standard surfaces the two read-by-attorneys fields:

| Field | Tier | Notes |
|---|---|---|
| `abstractHtml` | minimal+standard | Plus `abstractStart`/`abstractEnd` for PDF assembly. |
| `claimsHtml` | standard | ~4-10× the size of abstract on a typical record. Plus `claimsStart`/`claimsEnd`. |

Full carries: `descriptionHtml`, `briefHtml`, `backgroundTextHtml`, `subHeadingM0Html` through `subHeadingM6Html` (7 sub-heading variants), `claimStatement`, `claimsTextAmended`, `equivalentAbstractText`, `drawingDescription`, `statutoryInventionText`, `abstractedPatentNumber`, `abstractedPublicationDerwent`, `abstractHeader`.

### Counts (6 fields)

Standard surfaces:

| Field | Tier | Notes |
|---|---|---|
| `numberOfClaims` | standard | String, e.g. `"28"`. Null on PGPUB. |
| `numberOfDrawingSheets` | standard | String. Null on PGPUB. |
| `numberOfFigures` | standard | String. Null on PGPUB. |

Full carries: `numberOfPagesInSpecification`, `numberOfPagesOfSpecification`, `pageNumber`.

### Family + continuity (~30 fields)

Standard:

| Field | Tier | Notes |
|---|---|---|
| `familyIdentifierCur` | standard | Int. INPADOC-style. |
| `continuityData` | standard | List. Free-text on USPAT, structured chain on US-PGPUB. |

Full carries: `familyIdentifierCurStr`, `familyIdentifierOrig`, `auxFamilyMembersGroupTempPlaceHolder`, `continuedProsecutionAppl`, the 8-field `patentFamily*` group (`Country`, `Date`, `DocNumber`, `Kind`, `KindCode`, `Language`, `Members`, `Name`, `SerialNumber`), and the 16-field `relatedAppl*` group covering parents, children, and PCT relationships.

### Citations (~15 fields, full only)

`refCitedOthers`, `refCitedPatentDocCountryCode`, `refCitedPatentDocDate`, `refCitedPatentDocKindCode`, `refCitedPatentDocName`, `refCitedPatentDocNumber`, `refCitedPatentRelevantPassage`, `referenceCitedCode`/`Group`/`SearchPhase`/`Text`, `foreignRefCitationClassification`/`Cpc`, `foreignRefCountryCode`/`Group`/`PatentNumber`/`PubDate`, `citedPatentLiterature*` (4 fields), `usRefClassification`/`CpcClassification`/`Group`/`IssueDate`/`PatenteeName`.

If citations become a tooled use case, candidate tool: `ppubs_get_citations(guid)`.

### PCT / Hague international (~25 fields, full only)

`pct*` group (12 fields): `pct102eDate`, `pct371c124Date`, `pctFilingDate`, `pctFilingDocCountryCode`, `pctFilingKind`, `pctFilingNumber`, `pctName`, `pctOrRegionalPublishingCountry`/`Kind`/`Name`/`Serial`/`Text`, `pctPubDate`/`DocIdentifier`/`Number`.

`hagueIntl*` group (7 fields): `hagueIntlFilingDate`, `hagueIntlRegistrationDate`, `hagueIntlRegistrationNumber`, `hagueIntlRegistrationPubDate`, plus KWIC variants.

`designatedStates`, `designatedstatesRouteGroup`, `patentNumberOfLocalApplication`.

### Priority (~12 fields, full only)

`priorityApplYear`, `priorityApplicationCountry`, `priorityApplicationDate`, `priorityClaimsCountry`, `priorityClaimsDate`, `priorityClaimsDateSearch`, `priorityClaimsDocNumber`, `priorityCountryCode`, `priorityNumberDerived`, `priorityPatentDid`, `priorityPatentNumber`, `priorPublishedDoc*` (5 sub-fields).

### Reissue / corrections (~12 fields, full only)

`reissueAppl*` (3 fields), `reissueParent*` (5 fields), `reissuedPatentAppl*` (4 fields), `reissuePatentGroup`, `reissuePatentParentStatus`.

Flags: `certOfCorrectionFlag`, `ptabCertFlag`, `supplementalExaminationFlag`, `reexaminationFlag`, `affidavit130BFlag`, `rule47Flag`, `messengerDocsFlag`.

### Sequences / biological / polymer (~12 fields, full only)

`biologicalDepositInformation`, `depositAccessionNumber`, `depositDescription`, `sequenceCwu`, `sequenceListNewRules`, `sequenceListOldRules`, `sequencesListText`, `usBotanicLatinName`, `usBotanicVariety`, `polymerIndexingCodes`, `polymerMultipunchCodeRecordNumber`, `polymerMultipunchCodes`.

### Drawings (~10 fields)

Standard surfaces `drawingsStart`/`drawingsEnd`. Full carries: `numberOfDrawingSheets` (already in standard), `numberOfFigures` (standard), `chosenDrawingsReference`, `drawingDescription`, `selectedDrawingCharacter`, `selectedDrawingFigure`, `imageFileName`, `imageLocation`, `dwImage*`/`dwPage*` lists.

### Page-range pointers (28 fields, mostly full)

Standard surfaces 4 useful pairs only: `abstract`, `claims`, `specification`, `drawings`. Full adds: `amend`, `bib`, `certCorrection`, `certReexamination`, `frontPage`, `ptab`, `searchReport`, `supplemental`, `descriptionStart`/`End`.

### Derwent / third-party indexing (~12 fields, full only)

`derwentAccessionNumber`, `derwentClass`, `derwentClassAlpha`, `derwentWeek`, `derwentWeekInt`, `abstractedPublicationDerwent`, `newRecordPatentDerwent`, `nonCpiSecondaryAccessionNumber`, `cpiManualCodes`, `cpiSecondaryAccessionNumber`, `epiManualCodes`, `exchangeWeek`, `volumeNumber`, `editionField`, `ibmtdbAccessionNumber`, `unlinkedDerwentRegistryNumber`, `unlinkedRingIndexNumbersRarerFragments`, `pfDerwentWeekDate`, `pfDerwentWeekNum`, `pfDerwentWeekYear`.

### Government / statutory (full only)

`governmentInterest`, `affidavit130BText`, `securityLegend`, `termOfExtension`, `termOfPatentGrant`, `additionalIndexingTerm`, `standardTitleTerms`, `standardTitleTermsHighlights`, `titleTermsData`.

### KWIC highlights (~30 fields, never standard)

Search-side highlight metadata. Field name suffixes: `KwicHits`, `Highlights`. Examples: `applicationFilingDateKwicHits`, `applicationNumberHighlights`, `cpcAdditionalCurrentDateKwicHits`, `cpcAdditionalDateKwicHits`, `cpcInventiveCurrentDateKwicHits`, `cpcInventiveDateKwicHits`, `curIntlPatentClassificationNoninventionDateKwicHits`, `curIntlPatentClassificationPrimaryDateKwicHits`, `curIntlPatentClassificationSecHighlights`, `curIntlPatentClassificationSecondaryDateKwicHits`, `curIntlPatentClassifictionPrimaryDateKwicHits` (typo — both forms exist), `datePublishedKwicHits`, `foreignRefPubDateKwicHits`, `hagueIntlFilingDateKwicHits`, `hagueIntlRegistrationDateKwicHits`, `hagueIntlRegistrationPubDateKwicHits`, `inventionTitleHighlights`, `pct371c124DateKwicHits`, `pctFilingDateKwicHits`, `pctPubDateKwicHits`, `pfApplicationDateKwicHits`, `pfPublDateKwicHits`, `priorPublishedDocDateKwicHits`, `priorityClaimsDateKwicHits`, `relatedApplFilingDateKwicHits`, `relatedApplPatentIssueDateKwicHits`, `usRefIssueDateKwicHits`, etc.

---

## Field-naming gotchas

1. **`inventionTitle` not `title`** — and `publicationReferenceDocumentNumber` not `patentNumber` or `pubNumber`. PPUBS uses verbose Solr-friendly names.
2. **`inventorsName` (list) ≠ `inventorsShort` (string)** — both surface in detail standard. `inventorsShort` is `"X et al."`-style; `inventorsName` is the full list.
3. **`assigneeName` is empty pre-grant on US-PGPUB.** Use `applicantName` for application-time owner. They diverge on granted patents (often the company is the assignee, an individual is the applicant).
4. **Three forms of pub#**: `publicationReferenceDocumentNumber`, `publicationReferenceDocumentNumber1`, `publicationReferenceDocumentNumberOne`. We surface the canonical only; the other two are redundant.
5. **`applicationFilingDate` is a list** — multi-valued for continuation chains. Surface as `[<earliest>]` for triage.
6. **`numberOfClaims` is a string** — `"28"`, not `28`. Same for `numberOfDrawingSheets`, `numberOfFigures`. Cast at the consumer if you need an int.
7. **`familyIdentifierCur` shape varies**: traditional INPADOC families return small ints (e.g. `26732223`); newer applications carry 13-digit ints (e.g. `1000008228732`). Don't assume range.
8. **`primaryExaminer`/`assistantExaminer`/`numberOfClaims`/etc. null on US-PGPUB** — these populate at examination. A standard-tier filter on a published application returns null for these without dropping them; consumers should handle null.
9. **`continuityData` shape varies by source**: free-text English on USPAT (`"This application claims the benefit of..."`) vs structured chain on US-PGPUB (`"parent US continuation 18359258 20230726..."`). Parse accordingly.
10. **USPTO ships a typo in field naming**: `issuedUsDigestRefClassifi` (not `Classification`) appears alongside `issuedUsDigestRefClassification`. Both exist. Same with `curIntlPatentClassifictionPrimaryDateKwicHits` (`Classifiction`, missing `a`) alongside the correctly-spelled variant.

---

## Maintenance

- **When PPUBS adds a field**: probe with `curl` (see `memory://main/tetra/uspto/uspto-ppubs-wire-protocol-locked-2026-05-10-against-live-probe`), categorize it, decide tier, update both `RESPONSE_FIELDS` in `src/server.py` AND this file.
- **When PPUBS renames or removes a field**: same flow, plus consider whether it's a breaking change for `uspto-mcp` consumers.
- **When tiers are retuned**: live-smoke against both a granted patent (USPAT) and a recent published application (US-PGPUB) before committing — they exercise different field populations.
- **Source for new endpoints**: browser DevTools network tab on `https://ppubs.uspto.gov/pubwebapp/`. Click around the SPA, watch `XHR` calls. `riemannzeta/patent_mcp_server` is the reverse-engineered Python reference.

## See also

- [`README.md`](../README.md) — tool surface, deployment.
- [`CLAUDE.md`](../CLAUDE.md) — code conventions, architecture.
- `src/server.py:RESPONSE_FIELDS` — the source of truth for tier membership.
- `src/uspto_client.py` — wire-protocol implementation.
- BM `tetra/uspto/uspto-ppubs-wire-protocol-locked-2026-05-10-against-live-probe` — protocol reference (auth, endpoints).
- Reference port: [`riemannzeta/patent_mcp_server`](https://github.com/riemannzeta/patent_mcp_server) (MIT).
