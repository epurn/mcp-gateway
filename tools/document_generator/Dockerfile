FROM pandoc/extra

# Install Python and pip
RUN apk add --no-cache python3 py3-pip ttf-dejavu && \
    ln -sf python3 /usr/bin/python

# Create virtual environment for system package isolation
# This is recommended on modern Alpine/Python to avoid conflicts with apk-managed packages
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

# Create user (adduser syntax is different on Alpine)
RUN adduser -D appuser
USER appuser

EXPOSE 8000

# Reset entrypoint from base image (which is set to ["pandoc"])
ENTRYPOINT []

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
