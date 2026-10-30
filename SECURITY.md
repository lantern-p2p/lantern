# Security

Lantern is an experimental public beta and has not received an independent
security audit. Do not use it to transfer secrets or files whose disclosure
would cause harm.

The signaling service accepts room and WebRTC setup messages only. It does not
accept file payloads. A successful transfer uses the browser's encrypted
WebRTC data channel between the two peers. Google STUN is configured to help
peers discover a network path and may observe their public IP addresses. This
beta has no TURN relay, so some network configurations cannot connect.

Room codes are random, temporary, and intended to be shared only with the
recipient. Room state is held in memory and disappears when the service restarts
or its free hosting instance sleeps. The service applies basic origin, message,
connection, and room-creation limits, but does not yet have authentication,
durable distributed room state, or comprehensive abuse protection.

To report a security issue privately, use GitHub's **Report a vulnerability**
feature on the repository. Do not include sensitive files or live room codes in
public issues.
