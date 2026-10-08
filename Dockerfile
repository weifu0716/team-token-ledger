FROM python:3.12-slim
WORKDIR /app
COPY ledger /app/ledger
RUN useradd --uid 10001 --create-home ledger && mkdir /data && chown ledger:ledger /data
USER ledger
EXPOSE 8765
VOLUME ["/data"]
CMD ["python", "-m", "ledger", "server", "--data", "/data", "--host", "0.0.0.0"]
