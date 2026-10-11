# Duration visual polish

PRE_ITERATION_HEAD: 574ed24669e0662976569c87329ec7a0c01b7a88
Owner intent: presentation/direct UX only, on feature/adaptive-duration-slider.

Current audit: createDurationSlider creates header label/value/AUTO button plus range and secondary scale footer. Widget height is 70. Duration domain classifier, configurationOptions, semantic value setter/serializeValue, request conversion and relation projection already provide the functional contract.

Bounded UI change: retain label/current value/track/thumb; remove AUTO button, footer, permanent tick/min/max labels, background enclosure and instructional Default hint. Display Default only for semantic 0. Widget measurement becomes 42 (28 fewer graph units). Unverified/incompatible saved-value disclosures remain. A native node context-menu action, Reset Duration to model default, sets the same semantic 0 via the existing selection path, chains existing menu contributions and refreshes projection/pricing normally. No second permanent control.

Default, explicit seconds, snap constraints, classifier, range architecture, model/method/coupled projection and every Python production file remain unchanged. Scope is createDurationSlider plus Default-only presentation disclosure removal in configureDuration, focused frontend tests and documentation. Product Owner's textual target is the visual authority; no separate ByteDance screenshot was attached to this request.

Real canonical DEV 8189 and its source fingerprint were verified healthy before inspection. Frontend bytes matched the iteration baseline before deployment. Default/explicit persistence and reset must be demonstrated with new review workflows; no Generate/Run.
