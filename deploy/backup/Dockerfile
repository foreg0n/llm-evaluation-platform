FROM restic/restic:0.19.1 AS restic

FROM postgres:17-alpine

RUN apk add --no-cache ca-certificates tzdata \
    && mkdir -p /cache /repository /state /opt/evalflow-backup \
    && chown -R postgres:postgres /cache /repository /state /opt/evalflow-backup

COPY --from=restic /usr/bin/restic /usr/local/bin/restic
COPY --chown=postgres:postgres scripts/ /opt/evalflow-backup/
RUN chmod 0555 /opt/evalflow-backup/*.sh

ENV RESTIC_CACHE_DIR=/cache \
    RESTIC_HOST=evalflow-production \
    BACKUP_STATE_DIR=/state

USER postgres

ENTRYPOINT ["/opt/evalflow-backup/entrypoint.sh"]
CMD ["loop"]
