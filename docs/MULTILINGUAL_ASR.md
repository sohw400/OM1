# Multilingual ASR Support

OM1's Google ASR integration now supports multiple languages for speech recognition.

## Supported Languages

The following languages are currently supported:

| Language | Configuration Value | Language Code |
|----------|-------------------|---------------|
| English | `english` | en-US |
| Chinese (Simplified) | `chinese` | cmn-Hans-CN |
| German | `german` | de-DE |
| French | `french` | fr-FR |
| Japanese | `japanese` | ja-JP |
| Korean | `korean` | ko-KR |
| Spanish | `spanish` | es-ES |
| Italian | `italian` | it-IT |
| Portuguese (Brazilian) | `portuguese` | pt-BR |
| Russian | `russian` | ru-RU |
| Arabic (Saudi) | `arabic` | ar-SA |

## Configuration

To use a specific language for ASR, add the `language` parameter to your agent configuration:

```json
{
  "agent_inputs": [
    {
      "type": "GoogleASRInput",
      "config": {
        "api_key": "your_api_key",
        "language": "korean"
      }
    }
  ]
}
```

## Usage Examples

### Korean

```json
{
  "type": "GoogleASRInput",
  "config": {
    "language": "korean"
  }
}
```

### Spanish

```json
{
  "type": "GoogleASRInput",
  "config": {
    "language": "spanish"
  }
}
```

### Japanese

```json
{
  "type": "GoogleASRInput",
  "config": {
    "language": "japanese"
  }
}
```

## Language-Specific Notes

### Korean (ko-KR)
- Works well with clear pronunciation
- Best results with standard Korean dialect
- Handles both formal and informal speech patterns

### Chinese (cmn-Hans-CN)
- Optimized for Mandarin with Simplified Chinese characters
- May require additional testing for various dialects

### Arabic (ar-SA)
- Configured for Saudi Arabian dialect
- Other Arabic dialects may have varying accuracy

### Portuguese (pt-BR)
- Optimized for Brazilian Portuguese
- European Portuguese may require different configuration

## Default Behavior

If no language is specified or an unsupported language is configured, the system defaults to English (en-US) with a warning message in the logs:

```
Language <language> not supported. Current supported languages are: [...]. Defaulting to English
```

## Testing Your Language

To test ASR with your chosen language:

1. Configure the language in your agent's config file
2. Run OM1 with your agent configuration
3. Speak clearly into your microphone
4. Check the logs for recognition results

Example command:
```bash
uv run src/run.py your_agent_config
```

## Troubleshooting

**No recognition results:**
- Verify your microphone is working
- Check that the correct language is configured
- Ensure you're speaking clearly and at an appropriate volume
- Review logs for any error messages

**Poor accuracy:**
- Try speaking more clearly or slowly
- Check for background noise
- Verify the language code matches your dialect
- Ensure your microphone quality is adequate

**Language not working:**
- Confirm the language is in the supported list
- Check spelling of the language name in configuration
- Review logs for language initialization messages

## Adding New Languages

To add support for additional languages:

1. Find the appropriate Google Cloud Speech-to-Text language code from the [official documentation](https://cloud.google.com/speech-to-text/docs/languages)
2. Add the language to `LANGUAGE_CODE_MAP` in both:
   - `src/inputs/plugins/google_asr.py`
   - `src/inputs/plugins/google_asr_rtsp.py`
3. Update this documentation
4. Submit a pull request with test results

Example:
```python
LANGUAGE_CODE_MAP: dict = {
    # ... existing languages
    "hindi": "hi-IN",  # Add new language
}
```

## Performance Notes

- Recognition latency varies by language (typically 1-3 seconds)
- Some languages may have better accuracy than others
- Network connectivity affects all languages equally
- Background noise impacts all languages similarly

## API Key Requirements

All language support requires a valid OpenMind API key. Obtain yours at [OpenMind Portal](https://portal.openmind.org/).

## Related Issues

- Issue #359: Test OM1's ASR in Multiple Languages
- Addresses community requests for Korean language support

## License

This feature is part of OM1 and is released under the MIT License.
