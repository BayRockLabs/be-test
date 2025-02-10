# Stage 1: Build image
FROM python:3.9 AS builder

WORKDIR /c2c-service

COPY . .
COPY .env .env

RUN pip install --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt


# Stage 2: Final image
FROM python:3.9-slim

WORKDIR /c2c-service

COPY --from=builder /c2c-service /c2c-service

EXPOSE 8000

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
