# BoliCheck

**Hinglish voice counts for warehouse dispatch**

**Problem.** At a loading bay, a worker can report an item count aloud while a supervisor has the planned quantity on a manifest. If those numbers differ, someone needs to catch the discrepancy while the load can still be checked.

**Users.** Dispatch supervisors and loading staff at small warehouses, distributors and parcel hubs.

**Solution.** The supervisor selects a manifest item and records a short Hindi–English count. BoliCheck displays the transcript, extracts one supported whole number and checks it against the expected quantity. A difference holds the load. A phrase with two counts, such as “चौदह नहीं, चौबीस,” prompts a fresh count. After all rows match, the supervisor reviews the physical load and confirms handoff.

**Gnani AI.** The prototype integrates Prisma v3.0 speech-to-text over the REST API with Hindi and English language hints. It sends the recording for transcription and reconciles counts locally against the sample manifest. Practice mode is labeled and uses typed examples.

**Demonstration.** A fictional load expects 24 blue crates and 12 sealed cartons. A spoken count of 14 crates gives a shortage of 10. A clear recount of 24 resolves the crate row. The handoff becomes available after the carton count also matches.

**Scope.** One synthetic manifest, two item types and counts from 0 to 99. The supervisor checks the transcription and the load before confirming.
