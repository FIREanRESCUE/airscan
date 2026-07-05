# AirScan

AirScan is a unified digital radio scanner for RTL-SDR dongles. It wraps the open-source [DSD-neo](https://github.com/arancormonk/dsd-neo) decoder to monitor trunked and conventional systems across the major public-safety digital formats:

- **P25** Phase 1 and Phase 2 (including trunking)
- **DMR** Tier III, Capacity Plus, Connect Plus, and conventional
- **NXDN** 6.25 kHz and 12.5 kHz trunking

AirScan provides a desktop GUI for system configuration, talkgroup aliasing, channel maps, live activity logging, and per-call recording — similar in purpose to SDRTrunk or Unitrunker, but built around widely available RTL-SDR hardware and open-source decoding components.

## Architecture

AirScan does not reimplement vocoders or trunking logic from scratch. Instead it orchestrates **DSD-neo**, which already includes:

- Native RTL-SDR and RTL-TCP input
- Built-in P25/DMR/NXDN trunk following with automatic retune
- Channel map and talkgroup CSV support
- Per-call WAV recording

AirScan adds:

- A Windows-friendly setup wizard (downloads DSD-neo automatically)
- System and talkgroup editors
- Single-dongle trunk scan rotation across multiple systems
- Live call/event log panel

## Requirements

- Windows 10/11 (primary target; Linux/macOS may work with manual DSD-neo setup)
- Python 3.10+
- RTL-SDR dongle (e.g. Nooelec NESDR, RTL2832U-based sticks)
- **WinUSB driver** installed via [Zadig](https://zadig.akeo.ie/) for the RTL-SDR interface

## Quick Start

```powershell
cd "scanner program"
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python run.py
```

On first launch, the setup wizard downloads DSD-neo v2.3.0. You can also point AirScan at an existing `dsd-neo.exe`.

### Configure a system

1. Click **Add** and enter your control channel frequency in MHz.
2. Choose the protocol (P25 Trunk, DMR Trunk, NXDN48/96, etc.).
3. Add a **channel map** (`channel,frequency_mhz,note` per line) for trunked systems.
4. Add **talkgroups** (`id,mode,name` per line). Use `A` to allow, `B` to block.
5. Click **Start Selected System**.

Example channel and talkgroup CSV templates are in the `examples/` folder.

### Decode from a radio aux cable (Baofeng, scanner, etc.)

You can decode digital audio from any radio that outputs discriminator or speaker audio to your PC:

1. Connect the radio **speaker or earphone jack** to your PC **line-in or microphone** input using a 3.5 mm aux cable.
2. Click **Radio Aux** (or Add and choose **Radio aux / line-in** as the input source).
3. Select your Windows input device (e.g. *Microphone*, *Line In*, or *Stereo Mix*).
4. Choose the protocol or leave **Auto-detect**.
5. Tune the radio manually to the digital channel and click **Start Selected System**.

Tips for Baofeng and similar analog-FM radios:

- Use the **earphone output**, not the speaker, for cleaner audio levels.
- Start with **input boost 2–4** if decoding is weak or absent.
- Keep volume moderate — clipping distorts digital decoding.
- **Trunk following does not work** with a manually tuned Baofeng unless you add rigctl support via SDR++ or a programmable radio. For Baofeng use conventional mode and tune by hand.
- Best results come from a radio/scanner with a **discriminator tap** or dedicated digital audio output; speaker audio works but is less reliable.

## RTL-SDR tips

- Set **PPM correction** if your dongle drifts (typical values: -2 to +3).
- Use **gain 0** for automatic gain, or 20–40 for strong local signals.
- For marginal signals, consider feeding audio from SDR++ via TCP instead of direct RTL input (see DSD-neo docs).
- P25 Phase 2 and busy trunked systems benefit from a stronger CPU and good antenna placement.

## Trunk scan mode

If you only have **one RTL-SDR** but want to monitor multiple control channels, add several systems and use **Trunk Scan All**. DSD-neo rotates the tuner across configured targets. Traffic on inactive targets may be missed while the tuner is elsewhere.

## Recording

Enable **Record calls** in the sidebar. WAV files are saved to the `recordings/` directory using DSD-neo's per-call naming.

## Project structure

```
airscan/           Application source
  gui/             Desktop UI
  models.py        System and settings data models
  dsdneo_engine.py Decoder process management
  dsdneo_setup.py  DSD-neo download and verification
  csv_generator.py Channel map / talkgroup CSV writers
examples/          Sample CSV files
data/              Local config (gitignored)
recordings/        Call recordings (gitignored)
tools/             Downloaded DSD-neo binary (gitignored)
```

## Legal notice

Monitoring radio communications may be restricted or illegal in your jurisdiction. Only monitor frequencies you are authorized to receive. This software is for educational and authorized monitoring purposes.

## Credits

- [DSD-neo](https://github.com/arancormonk/dsd-neo) — digital voice decoding engine
- [DSD / DSD-FME](https://github.com/lwvmobile/dsd-fme) — original decoder lineage
- [SDRTrunk](https://github.com/DSheirer/sdrtrunk) — architectural inspiration

## License

MIT
