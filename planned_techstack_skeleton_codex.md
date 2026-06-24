 AI-Callbot-Vinfast/
    README.md
    requirements.txt
    .env.example

    docs/
      ARCHITECTURE.md
      EVALUATION_REPORT.md

    src/
      callbot/
        __init__.py

        main.py                 # CLI entrypoint for live bot
        config.py               # env/config loading

        audio/
          recorder.py           # microphone capture
          playback.py           # optional TTS playback

        asr/
          base.py               # ASR interface
          faster_whisper_asr.py # Faster-Whisper implementation

        tts/
          base.py               # TTS interface
          edge_tts.py           # optional implementation

        llm/
          base.py               # LLM interface
          ollama_client.py      # Ollama wrapper
          prompts.py            # system prompts, extraction prompts

        dialogue/
          categories.py         # G_1 to G_5 schemas and required fields
          state.py              # call state, collected fields, turn history
          manager.py            # main dialogue orchestration
          intent.py             # category routing / ambiguity handling
          extraction.py         # structured field extraction
          exceptions.py         # emergency, stuck, garbled, hangup handling
          post_call.py          # summary, sentiment, emergency output

        models/
          schemas.py            # Pydantic models for final JSON

        utils/
          logging.py
          latency.py

    scenarios/
      g1_roadside_rescue.json
      g2_warranty_repair.json
      g3_order_status.json
      g4_motorbike_warranty.json
      g5_remote_tech_support.json
      exceptions.json

    tests/
      test_dialogue_state.py
      test_field_extraction.py
      test_exception_handling.py
      test_final_output_schema.py

    eval/
      run_eval.py               # runs scripted test scenarios
      metrics.py                # field accuracy, category accuracy, latency
      report_template.md

  Core Design

  Use a controlled dialogue manager instead of letting the LLM run the whole conversation freely.

  Each turn should follow this flow:

  microphone audio
    -> ASR transcript
    -> dialogue manager
        -> detect emergency / hangup / garbled input
        -> classify or confirm category
        -> extract fields
        -> update state
        -> decide next missing field or final action
        -> generate Vietnamese response
    -> text response
    -> optional TTS

  The final call output should always be generated from state:

  {
    "category": "G_1",
    "fields": {
      "full_name": "...",
      "phone": "...",
      "vehicle_model": "...",
      "license_plate_vin": "...",
      "vehicle_type": "...",
      "current_odo": "...",
      "current_location": "...",
      "city_name": "...",
      "vehicle_condition": "..."
    },
    "post_call": {
      "short_summary": "...",
      "sentimental_analysis": "...",
      "emergency": "yes"
    }
  }

  Implementation Priority

  1. Build schemas for all 5 categories.
  2. Build text-only dialogue manager first.
  3. Add LLM wrapper and prompts for:
      - category classification
      - field extraction
      - response generation
      - post-call summary

  4. Add ASR microphone path.
  5. Add evaluation runner with at least 10 happy-path scenarios plus exception cases.
  6. Add optional TTS last.