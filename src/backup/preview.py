"""Bounded archive listing; never extract backup members to a filesystem."""
import io
import tarfile


def archive_listing(content):
    lines = ["Type       Mode     Size       Path"]
    truncated = False
    with tarfile.open(fileobj=io.BytesIO(content), mode="r:*") as archive:
        for index, member in enumerate(archive):
            if index >= 2000:
                truncated = True; break
            name = member.name[:400].encode("unicode_escape").decode("ascii")
            kind = "symlink" if member.issym() else "hardlink" if member.islnk() else "directory" if member.isdir() else "file" if member.isfile() else "special"
            if member.issym() or member.islnk():
                target = member.linkname[:400].encode("unicode_escape").decode("ascii")
                name += " -> " + target
            line = f"{kind:10s} {member.mode:04o}     {member.size:10d} {name}"
            if sum(len(item) + 1 for item in lines) + len(line) > 65500:
                truncated = True; break
            lines.append(line)
    return {"text": "\n".join(lines), "truncated": truncated, "bytes": len(content)}
