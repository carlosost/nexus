The comment text on line 50 contains "USER appuser" — my `lineno` helper returns first match including comments. Fix the verifier to skip comment lines for Dockerfile directives:All three files verified. Here's exactly what changed and why each fix works:

---

**Dockerfile** — two surgical additions in Stage 2, as root, before `USER appuser`:

```
COPY --from=builder /install /usr/local       ← spacy binary now on PATH
RUN python -m spacy download en_core_web_sm  ← baked into image layer (Gap 1)
...
RUN mkdir -p /app/media/resumes \             ← seeds named-volume ownership (Gap 2)
    && chown -R appuser:appuser /app
USER appuser
```

The model download happens in Stage 2 (not Stage 1) so it can use the just-copied `spacy` binary. It's a proper image layer — cached after the first `--build`, never re-downloaded on `docker compose up`.

---

**scripts/entrypoint.sh** — media directory guard added as Step 0:

```bash
mkdir -p /app/media/resumes 2>/dev/null || true
```

The `|| true` is load-bearing: in dev, the bind-mount at `/app` may be host-owned and block `mkdir` on the parent path. The named volume already provides the writable directory at that exact path, so the failure is safely suppressed. For bare `docker run` deployments without compose, it succeeds and creates the path.

---

**docker-compose.yml** — named volume appended after the bind-mount:

```yaml
volumes:
  - .:/app                                          # dev bind-mount
  - local_resume_media:/app/media/resumes          # shadows it here
```

Docker applies mounts in declaration order. The named volume wins at `/app/media/resumes`, giving `appuser` a Docker-managed directory with correct ownership regardless of host UID — the bind-mount at `/app` cannot interfere with it. `start_period` bumped from 30s → 45s to account for migrate + seed_demo completing before the healthcheck fires.