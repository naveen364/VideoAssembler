"""
Piper TTS — Local HTTP Server
Free, offline text-to-speech for VideoAssembler.
Runs on port 5050, returns WAV audio.
"""

import io
import os
import wave
import json
import subprocess
from pathlib import Path
from flask import Flask, request, jsonify, send_file, Response
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

MODELS_DIR = Path(os.environ.get("MODELS_DIR", "/app/models"))
DEFAULT_VOICE = os.environ.get("DEFAULT_VOICE", "en_US-amy-medium")

# Voice catalog — name → download URL stub
# Piper auto-downloads from Hugging Face via the CLI
VOICE_CATALOG = {
    "en_US-amy-medium": {
        "label": "Amy (Female, American)",
        "quality": "medium",
        "language": "en_US"
    },
    "en_US-lessac-medium": {
        "label": "Lessac (Male, American)",
        "quality": "medium",
        "language": "en_US"
    },
    "en_US-ryan-medium": {
        "label": "Ryan (Male, American)",
        "quality": "medium",
        "language": "en_US"
    },
    "en_US-kusal-medium": {
        "label": "Kusal (Male, American)",
        "quality": "medium",
        "language": "en_US"
    },
    "en_GB-alba-medium": {
        "label": "Alba (Female, British)",
        "quality": "medium",
        "language": "en_GB"
    },
    "en_GB-aru-medium": {
        "label": "Aru (Male, British)",
        "quality": "medium",
        "language": "en_GB"
    },
    "en_US-amy-low": {
        "label": "Amy (Female, Fast/Low)",
        "quality": "low",
        "language": "en_US"
    },
    "en_US-lessac-high": {
        "label": "Lessac (Male, High Quality)",
        "quality": "high",
        "language": "en_US"
    },
}


def get_model_path(voice_name):
    """Return the path to the ONNX model file, downloading if needed."""
    model_dir = MODELS_DIR / voice_name
    onnx_file = model_dir / f"{voice_name}.onnx"

    if onnx_file.exists():
        return str(onnx_file)

    # Try to find it via piper's default download location
    # piper-tts downloads to ~/.local/share/piper_models/ by default
    alt_paths = [
        Path.home() / ".local" / "share" / "piper_models" / voice_name / f"{voice_name}.onnx",
        MODELS_DIR / f"{voice_name}.onnx",
    ]
    for p in alt_paths:
        if p.exists():
            return str(p)

    return None


def synthesize_with_piper(text, voice_name, speed=1.0):
    """
    Run piper CLI to synthesize text to WAV.
    Uses --download-dir to auto-download missing models.
    Returns WAV bytes.
    """
    cmd = [
        "piper",
        "--model", voice_name,
        "--download-dir", str(MODELS_DIR),
        "--data-dir", str(MODELS_DIR),
        "--output-raw",
        "--length-scale", str(1.0 / speed if speed > 0 else 1.0),
    ]

    proc = subprocess.run(
        cmd,
        input=text.encode("utf-8"),
        capture_output=True,
        timeout=120,
    )

    if proc.returncode != 0:
        stderr = proc.stderr.decode("utf-8", errors="replace")
        raise RuntimeError(f"Piper failed (code {proc.returncode}): {stderr}")

    raw_pcm = proc.stdout
    if len(raw_pcm) == 0:
        raise RuntimeError("Piper produced no audio output")

    # Wrap raw PCM (16-bit, mono, 22050Hz) in a WAV container
    sample_rate = 22050
    sample_width = 2  # 16-bit
    channels = 1

    wav_buf = io.BytesIO()
    with wave.open(wav_buf, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(sample_rate)
        wf.writeframes(raw_pcm)

    wav_buf.seek(0)
    return wav_buf


@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint."""
    return jsonify({
        "status": "ok",
        "engine": "piper-tts",
        "default_voice": DEFAULT_VOICE,
    })


@app.route("/voices", methods=["GET"])
def list_voices():
    """List available voices."""
    voices = []
    for name, info in VOICE_CATALOG.items():
        voices.append({
            "id": name,
            "label": info["label"],
            "quality": info["quality"],
            "language": info["language"],
        })
    return jsonify({"voices": voices})


@app.route("/synthesize", methods=["POST"])
def synthesize():
    """
    Synthesize speech from text.
    Body: { "text": "Hello world", "voice": "en_US-amy-medium", "speed": 1.0 }
    Returns: audio/wav
    """
    data = request.get_json(force=True)
    text = data.get("text", "").strip()
    voice = data.get("voice", DEFAULT_VOICE)
    speed = float(data.get("speed", 1.0))

    if not text:
        return jsonify({"error": "No text provided"}), 400

    # Validate voice name to prevent command injection
    if voice not in VOICE_CATALOG:
        return jsonify({
            "error": f"Unknown voice: {voice}",
            "available": list(VOICE_CATALOG.keys())
        }), 400

    try:
        app.logger.info(f"Synthesizing: voice={voice}, speed={speed}, text_len={len(text)}")
        wav_buf = synthesize_with_piper(text, voice, speed)
        return send_file(
            wav_buf,
            mimetype="audio/wav",
            as_attachment=False,
            download_name="speech.wav",
        )
    except Exception as e:
        app.logger.error(f"Synthesis failed: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/synthesize", methods=["OPTIONS"])
def synthesize_options():
    """Handle CORS preflight."""
    return Response(status=200)


if __name__ == "__main__":
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    port = int(os.environ.get("PORT", 5050))
    print(f"🔊 Piper TTS Server starting on port {port}")
    print(f"📁 Models directory: {MODELS_DIR}")
    print(f"🎙️ Default voice: {DEFAULT_VOICE}")
    print(f"📋 Available voices: {', '.join(VOICE_CATALOG.keys())}")

    # Pre-download the default voice model
    print(f"⏳ Pre-downloading default voice model '{DEFAULT_VOICE}'...")
    try:
        synthesize_with_piper("Initialization complete.", DEFAULT_VOICE)
        print(f"✅ Default voice ready!")
    except Exception as e:
        print(f"⚠️  Could not pre-download voice (will retry on first request): {e}")

    app.run(host="0.0.0.0", port=port, debug=False)
