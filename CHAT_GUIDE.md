# machine-state chat — What You Can Ask

All queries go through `npm run chat -- "<your question>"`.
The system detects intent automatically — no special syntax needed.

---

## RAM & Memory

```bash
npm run chat -- "How much RAM am I using?"
npm run chat -- "How much memory is available?"
npm run chat -- "What is my memory pressure right now?"
```

---

## Disk & Storage

```bash
npm run chat -- "How much disk space do I have left?"
npm run chat -- "What is my storage usage?"
npm run chat -- "What can I clean up to free space?"
npm run chat -- "Give me a storage breakdown by category."
```

---

## Performance & Slowdowns

```bash
npm run chat -- "Why is my machine slow?"
npm run chat -- "Why is everything laggy?"
npm run chat -- "What is hogging all my resources?"
npm run chat -- "What is slowing my Mac down?"
```

---

## Restart / Shutdown Safety

```bash
npm run chat -- "Is it safe to restart my computer right now?"
npm run chat -- "Can I restart now?"
npm run chat -- "Should I reboot?"
npm run chat -- "Safe to shut down?"
```

---

## System Health

```bash
npm run chat -- "Is my system healthy?"
npm run chat -- "How is my machine doing overall?"
npm run chat -- "Give me a system status summary."
```

---

## Pressure Analysis

```bash
npm run chat -- "What is my RAM pressure?"
npm run chat -- "What is my disk pressure?"
npm run chat -- "What is the current pressure level?"
```

---

## Install Feasibility

```bash
npm run chat -- "Can I install Xcode?"
npm run chat -- "Will a 25GB game fit on my disk?"
npm run chat -- "Do I have enough space for Final Cut Pro?"
npm run chat -- "Can I install this 40GB application?"
```

---

## Compatibility Check

```bash
npm run chat -- "Can I run Photoshop on my machine?"
npm run chat -- "Will GTA 5 work on my Mac?"
npm run chat -- "Can I run this app?"
```

---

## App Profiles

```bash
npm run chat -- "Tell me about Chrome."
npm run chat -- "How much memory does Slack use?"
npm run chat -- "Give me a profile of Docker."
npm run chat -- "Info about Xcode."
```

---

## Usage Patterns & Activity

```bash
npm run chat -- "What apps do I use the most?"
npm run chat -- "What are my peak usage hours?"
npm run chat -- "Show me my activity patterns."
npm run chat -- "What are my dominant applications?"
```

---

## Forecasting — Disk

```bash
npm run chat -- "When will my disk fill up?"
npm run chat -- "How fast is my disk filling?"
npm run chat -- "What is my disk growth rate?"
npm run chat -- "How long until my disk runs out?"
```

---

## Forecasting — RAM

```bash
npm run chat -- "What is my RAM trajectory?"
npm run chat -- "Will my RAM fill up soon?"
npm run chat -- "Predict my memory usage."
npm run chat -- "How fast is my memory growing?"
```

---

## Install Impact Simulation

```bash
npm run chat -- "What happens if I install a 30GB game?"
npm run chat -- "Simulate installing a 50GB application."
npm run chat -- "What is the long-term disk impact of installing this?"
```

---

## Workload Patterns

```bash
npm run chat -- "When does my machine get slow?"
npm run chat -- "What time of day is my system slowest?"
npm run chat -- "Show me my workload patterns."
npm run chat -- "Are there recurring slowdowns?"
```

---

## Trends & Risk

```bash
npm run chat -- "What are my system trends?"
npm run chat -- "What is my overall risk score?"
npm run chat -- "Give me proactive insights about my machine."
npm run chat -- "What should I watch out for?"
npm run chat -- "Give me a predictive health summary."
```

---

## Verbose Mode

Shows the detected intent, provider, and token count after the response.

```bash
npm run chat:verbose -- "Why is my machine slow?"
npm run chat:verbose -- "How much disk space do I have?"
```

---

## Raw Mode

Outputs full JSON including the structured context passed to the model.

```bash
npm run chat:raw -- "Why is my machine slow?"
npm run chat:raw -- "What is my risk score?"
```

---

## Tips

- The system runs on **Ollama (`qwen3:8b`)** locally — no internet needed.
- All answers are based on **real collected snapshots**, not guesses.
- Run `npm run collect` first if you haven't taken a snapshot yet.
