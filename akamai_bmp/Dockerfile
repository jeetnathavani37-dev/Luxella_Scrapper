FROM golang:1.22-alpine AS build
WORKDIR /src
COPY . .
RUN go build -o /bmp ./cmd/akamai-bmp-server

FROM alpine:3.20
COPY --from=build /bmp /akamai-bmp
COPY db/devices.json /db/devices.json
EXPOSE 1337
ENTRYPOINT ["/akamai-bmp", "-host", "0.0.0.0", "-port", "1337", "-devicepath", "/db/devices.json"]
