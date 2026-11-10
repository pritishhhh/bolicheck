# BoliCheck

BoliCheck compares spoken Hinglish dispatch counts with a loading manifest. A supervisor selects an item, records the count, checks what Gnani Prisma heard and resolves any discrepancy before confirming handoff.

**Demo load BC-042** has 24 blue crates and 12 sealed cartons. Try a short count of 14 crates, a self-correction containing two counts, then one clear count for each item.

- [One-page solution pitch](PITCH.md)
- [Demo script and submission checklist](DEMO.md)

## Start locally on Windows

Open PowerShell in this folder. Python 3.10 or newer is required. The project has no packages to install.

```powershell
python bolicheck.py
```

Open [BoliCheck](http://127.0.0.1:8765) in Chrome or Edge. **Practice** uses example transcripts. Choose an example and press **Check transcript**. This mode exercises reconciliation without sending audio anywhere.

## Use Gnani speech

Get a Speech API key from the [Gnani console](https://app.gnani.ai/voice). Stop the practice server with Ctrl+C and run:

```powershell
python bolicheck.py --live
```

If you have a private `.env` file with `GNANI_API_KEY` beside `bolicheck.py`, the app loads it in live mode. Otherwise, paste your key at the hidden terminal prompt. Keep `.env` out of public uploads. The page opens in **Gnani speech** mode on refresh. Record a short count or upload a WAV or MP3. Only use scripted audio from consenting participants and a fictional manifest.

The server defaults to `prisma-v3.0`, using `hi-IN,en-IN` language hints and `transcribe` output for numbers. If your key only supports v2.5, select it explicitly before launching and report that model in your demo and pitch. V2.5 uses `hi-IN`.

```powershell
$env:GNANI_MODEL = 'prisma-v2.5'
python bolicheck.py --live
```

To return to v3.0, run `Remove-Item Env:GNANI_MODEL` and restart. Use `--port 8766` if the default port is busy.

## Deploy on Vercel

Import the repository into Vercel with the configuration in `vercel.json`. Practice mode is public. To enable Gnani speech, set `GNANI_API_KEY` and a separate random `BOLICHECK_VOICE_CODE` as sensitive production environment variables, then redeploy. Share the demo code privately with reviewers who need live speech. Keep the Gnani key in the Vercel environment and your ignored local `.env` file.

## How it works

1. The browser converts a clip to mono 16 kHz WAV and sends it to the local server.
2. The server calls [Gnani’s Prisma REST transcription API](https://docs.gnani.ai/api/STT/speech-to-text). It sends the audio and language settings, keeping the manifest quantities local.
3. A count rule accepts one supported whole number from 0 to 99 in a short phrase. The app flags differences and asks for a recount when a phrase contains conflicting numbers, uncertainty, or words outside the supported count vocabulary.
4. The operator checks the transcript against the actual load and manually confirms once both rows match. The prototype keeps the handoff state in the current page. Refreshing resets it.

Speech recognition can still confidently return the wrong single number. The transcript and manual check are part of the workflow. The app uses a fixed sample manifest and demonstrates the handoff decision locally.

## Verify the count rules

```powershell
python verify.py
```

The script checks transcript rules and uses a stubbed response to verify the request shape and the local speech endpoint. For real speech evidence, run the small audio check in [DEMO.md](DEMO.md) with your own API key and record the observed outcomes.
