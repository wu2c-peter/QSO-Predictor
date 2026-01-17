# QSO Predictor Session Notes
**Date:** January 17, 2025  
**Version:** 2.0.10  
**Session:** Windows UDP forwarding fix (Brian's issue)

---

## Overview

Fixed a Windows-specific bug where UDP forwarding to a closed port would kill the entire UDP listener, causing QSO Predictor to stop receiving data from WSJT-X/JTDX.

---

## The Problem

**User report:** Brian (KB1OPD) reported that QSO Predictor would receive a few decodes then stop working.

**Log evidence:**
```
INFO  | UDP: Bound to port 2238
INFO  | UDP: First status received - freq=7074000, dx_call=(none)
INFO  | UDP: First decode received - 0149 KI5ZND -12dB 1047Hz
WARNING | UDP: Socket error in listen loop: [WinError 10054] An existing connection was forcibly closed by the remote host
```

**Root cause:** Windows quirk with UDP sockets:
1. QSO Predictor receives packet from WSJT-X ✅
2. QSO Predictor forwards packet to another port (e.g., for GridTracker)
3. If nothing is listening on that port, Windows receives ICMP "port unreachable"
4. On the NEXT `recvfrom()` call, Windows throws error 10054
5. Our code caught this as OSError and **broke out of the listen loop**

This is a known Windows behavior - see: https://stackoverflow.com/questions/34242622/windows-udp-sockets-recvfrom-fails-with-error-10054

---

## The Fix

### 1. SIO_UDP_CONNRESET ioctl (Primary fix)

```python
if platform.system() == 'Windows':
    # Disable ICMP "port unreachable" errors from killing the socket
    SIO_UDP_CONNRESET = 0x9800000C
    self.sock.ioctl(SIO_UDP_CONNRESET, False)
    logger.debug("UDP: Disabled Windows ICMP connection reset errors")
```

This tells Windows: "Don't report ICMP errors on this UDP socket" - the standard fix used by other applications.

### 2. Graceful error handling (Fallback)

```python
except OSError as e:
    error_code = getattr(e, 'winerror', None) or getattr(e, 'errno', None)
    if error_code == 10054:
        # WSAECONNRESET - can safely ignore and continue
        logger.debug("UDP: Ignoring Windows ICMP connection reset")
        continue  # Don't break - keep listening!
    else:
        logger.warning(f"UDP: Socket error in listen loop: {e}")
        break
```

If the ioctl doesn't work for some reason, we catch error 10054 specifically and continue listening.

### 3. Self-forward detection

```python
if port == self.port:
    if port not in self._forward_errors_logged:
        logger.warning(f"UDP: Skipping forward to own port {port} (would cause loop)")
        self._forward_errors_logged.add(port)
    continue
```

Prevents accidental infinite loop if user configures forward port = listen port.

### 4. One-time error logging per port

```python
if port not in self._forward_errors_logged:
    logger.info(f"UDP: Forward to port {port} - target not listening (will retry silently)")
    self._forward_errors_logged.add(port)
```

Logs the first forward failure per port, then stays quiet to avoid spam.

### 5. Log forward configuration at startup

```python
if self.forward_ports:
    logger.info(f"UDP: Forwarding enabled to ports: {self.forward_ports}")
```

Makes it visible in logs what forwarding is configured.

---

## Files Modified

| File | Changes |
|------|---------|
| `udp_handler.py` | SIO_UDP_CONNRESET fix, graceful error handling, self-forward detection |

---

## Testing

### To verify the fix:
1. Configure QSO Predictor to forward to a port with nothing listening
2. Start WSJT-X/JTDX
3. Decodes should continue flowing even though forward target is closed
4. Log should show: "UDP: Forward to port XXXX - target not listening (will retry silently)"

### Expected log output (fixed):
```
INFO  | UDP: Bound to port 2238
INFO  | UDP: Forwarding enabled to ports: [2237]
INFO  | UDP: Listener thread started
INFO  | UDP: First status received - freq=14074000, dx_call=(none)
INFO  | UDP: First decode received - 1234 W1ABC -12dB 1500Hz
INFO  | UDP: Forward to port 2237 - target not listening (will retry silently)
... (decodes continue flowing)
```

---

## Version History Update

### v2.0.10 (January 2025)
- **Fixed:** Windows UDP socket dying when forwarding to closed port (Error 10054)
- **Fixed:** Self-forward detection prevents accidental loops
- **Improved:** Forward errors logged once per port instead of spamming
- **Improved:** Forward port configuration shown in startup log

---

## Commit Message

```
v2.0.10: Fix Windows UDP forwarding error 10054

BUG FIX:
- Fixed Windows-specific issue where forwarding UDP packets to a closed
  port would kill the entire UDP listener (WinError 10054)
- Applied SIO_UDP_CONNRESET ioctl to disable ICMP error reporting
- Added fallback to catch and ignore error 10054 if ioctl fails

IMPROVEMENTS:
- Self-forward detection prevents accidental loops (forward port = listen port)
- Forward errors logged once per port to avoid log spam
- Forward port configuration shown at startup for easier debugging

Thanks to Brian KB1OPD for the detailed log that identified this issue.

73 de WU2C
```

---

## Reply to Brian

```
Hi Brian,

Found it! The log was exactly what we needed.

The problem: Windows has a quirk where if QSO Predictor forwards UDP packets 
to a port with nothing listening, Windows kills the entire UDP socket. That's 
why you'd get a few decodes then it would stop.

I've fixed this in v2.0.10 - it now:
1. Tells Windows not to report these errors (proper fix)
2. Catches and ignores the error if it happens anyway (belt & suspenders)
3. Logs once that the forward target isn't listening, then stays quiet

Can you test when you get a chance? The new version should keep receiving 
decodes even if your forward target (GridTracker?) isn't running.

73,
Peter WU2C
```

---

## Technical Notes

### Why other apps don't have this problem:

1. **JTAlert, GridTracker, etc.** - Likely use `SIO_UDP_CONNRESET` ioctl
2. **Some apps** - Use separate socket for sending vs receiving
3. **Some apps** - Just ignore the error and reconnect

### The Windows UDP quirk explained:

On Linux/macOS, `sendto()` to a closed port just silently fails. On Windows:
1. `sendto()` succeeds (packet is sent)
2. Remote host returns ICMP "port unreachable"
3. Windows queues this error
4. Next `recvfrom()` returns the error instead of waiting for data

The `SIO_UDP_CONNRESET` ioctl (introduced in Windows XP SP2) disables this behavior.

---

**73 de WU2C**
