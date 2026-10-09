import io
import tarfile
from backup.preview import archive_listing


def test_archive_listing_does_not_return_file_contents():
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        member = tarfile.TarInfo("etc/sudoers"); member.size = 6; member.mode = 0o440
        archive.addfile(member, io.BytesIO(b"secret"))
    result = archive_listing(buffer.getvalue())
    assert "etc/sudoers" in result["text"] and "0440" in result["text"]
    assert "secret" not in result["text"] and not result["truncated"]


def test_archive_listing_identifies_links_and_escapes_target_controls():
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        for kind, name in [(tarfile.SYMTYPE, "etc/link"), (tarfile.LNKTYPE, "etc/hardlink")]:
            member = tarfile.TarInfo(name); member.type = kind; member.linkname = "target\nname"
            archive.addfile(member)
    result = archive_listing(buffer.getvalue())
    assert "symlink" in result["text"] and "hardlink" in result["text"]
    assert "etc/link -> target\\nname" in result["text"]
    assert len(result["text"].splitlines()) == 3
