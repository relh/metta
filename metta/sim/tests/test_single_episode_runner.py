from metta.sim.single_episode_runner import _is_presigned_url


def test_is_presigned_url_sigv4():
    url = "https://bucket.s3.amazonaws.com/key?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=xxx"
    assert _is_presigned_url(url) is True


def test_is_presigned_url_sigv2():
    url = "https://bucket.s3.amazonaws.com/key?AWSAccessKeyId=xxx&Signature=yyy"
    assert _is_presigned_url(url) is True


def test_is_presigned_url_regular_https():
    url = "https://example.com/file.json"
    assert _is_presigned_url(url) is False


def test_is_presigned_url_s3_scheme():
    url = "s3://bucket/key"
    assert _is_presigned_url(url) is False
