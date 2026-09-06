# Mobile proof

A deliberately thin Expo client proving that a native surface can open the real
`/v1/review`, preserve its canonical order, show company detail, and complete the same
server-owned review as the web app.

Set `EXPO_PUBLIC_API_URL` to an API address reachable from the device. In demo mode no
token is needed. The API client accepts a bearer session, and its transport is covered by
tests, but this proof deliberately does not read a token from an `EXPO_PUBLIC_` variable:
Expo embeds those values in the client bundle, so that would disclose the session.

Run `make run` in this directory and open the app with Expo Go. A production mobile app
would add operating-system-backed token storage, rotation and a complete authentication
journey first.
