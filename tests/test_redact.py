from envfix.redact import redact_secrets

def test_aws_key_redaction():
    text = "Error: Invalid token AKIAIOSFODNN7EXAMPLE for user."
    redacted = redact_secrets(text)
    assert redacted == "Error: Invalid token [REDACTED:AWS_KEY] for user."

    # Make sure it doesn't over-redact normal strings
    normal_text = "AKIA is not a key AKI"
    assert redact_secrets(normal_text) == normal_text

def test_jwt_redaction():
    text = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
    redacted = redact_secrets(text)
    assert redacted == "Authorization: Bearer [REDACTED:JWT]"

def test_db_url_redaction():
    text1 = "Connecting to postgres://admin:super_secret@localhost:5432/mydb"
    assert redact_secrets(text1) == "Connecting to postgres://[REDACTED_CREDENTIALS]@localhost:5432/mydb"

    text2 = "Failed mongodb+srv://dbuser:P@ssword123@cluster0.mongodb.net/admin"
    assert redact_secrets(text2) == "Failed mongodb+srv://[REDACTED_CREDENTIALS]@cluster0.mongodb.net/admin"

def test_private_key_redaction():
    key_text = '''
Some error happened here
-----BEGIN RSA PRIVATE KEY-----
MIIEowIBAAKCAQEA3
some fake base64 data here
-----END RSA PRIVATE KEY-----
And then some more trace.
'''
    redacted = redact_secrets(key_text)
    assert "[REDACTED:PRIVATE_KEY]" in redacted
    assert "MIIEowIBAAKCAQEA3" not in redacted
    assert "Some error happened here" in redacted
    assert "And then some more trace" in redacted

def test_generic_assignment_redaction():
    # Test with quotes
    text1 = 'API_KEY="my_fake_api_key_1234567890abcdefghijKLMNOPQRSTUV"'
    assert redact_secrets(text1) == 'API_KEY="[REDACTED:SECRET]"'

    # Test with single quotes and spaces
    text2 = "secret : 'my_fake_secret_1234567890abcdefghijKLMNOPQRSTUV'"
    assert redact_secrets(text2) == "secret : '[REDACTED:SECRET]'"

    # Test without quotes
    text3 = "export PASSWORD=supersecretpassword1234567890"
    assert redact_secrets(text3) == "export PASSWORD=[REDACTED:SECRET]"

    # Short string should NOT be redacted
    text4 = "export API_KEY=short123"
    assert redact_secrets(text4) == text4
