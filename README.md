# StintLab

**Motorsport telemetry, strategy and race engineering — built for sim racing.**

StintLab is an **open-source motorsport telemetry and race strategy application** designed to bring a lightweight race-engineering workflow to sim racing.

The project is currently in **active development**. At the moment, StintLab supports **Gran Turismo 7 (GT7)** telemetry, with support for additional racing platforms planned for the future.

> **Status:** Early development
> **Current telemetry platform:** Gran Turismo 7
> **License:** TBD



## What is StintLab?

StintLab aims to provide a single workspace for the information a driver or race engineer needs during a session.

The long-term goal is to combine:

* Real-time telemetry
* Tyre and stint management
* Fuel and pit strategy
* Race information
* Telemetry analysis
* Race strategy
* Pit-wall style information
* Support for multiple racing platforms

Rather than being tied to a single simulator, the project is being designed with a **platform-independent architecture**, allowing additional telemetry sources to be integrated over time.



## Current Platform Support

### Gran Turismo 7

GT7 is currently the **only supported racing platform**.

StintLab receives telemetry from Gran Turismo 7 over the local network and processes the data for use inside the application.

Current development includes:

* Real-time UDP telemetry
* Automatic GT7 telemetry discovery
* Telemetry packet decoding
* Lap and race information
* Tyre information
* Driver inputs
* Race strategy data
* Real-time communication between the telemetry service and the application

Additional GT7 telemetry fields are being progressively implemented and validated.



## Roadmap

StintLab is being developed incrementally.

### Telemetry

* [x] GT7 telemetry connection
* [x] UDP telemetry reception
* [x] Automatic GT7 discovery
* [x] Telemetry processing
* [ ] Complete GT7 telemetry decoding
* [ ] Telemetry recording
* [ ] Session replay
* [ ] Historical telemetry analysis

### Race Engineering

* [ ] Live race dashboard
* [ ] Lap timing
* [ ] Tyre strategy
* [x] Pit-stop strategy
* [x] Fuel strategy
* [x] Stint management
* [ ] Driver performance analysis
* [x] Race engineer / pit-wall views

### Platform Support

* [x] Gran Turismo 7
* [ ] Assetto Corsa
* [ ] Assetto Corsa Competizione
* [ ] iRacing
* [ ] F1
* [ ] Other platforms

Platform support will depend on the telemetry interfaces and APIs exposed by each simulator.

### Application

* [x] Electron desktop application
* [x] Keyboard shortcuts
* [ ] Production-ready builds
* [ ] Application auto-update
* [ ] Customizable workspace
* [ ] Cross-platform support



## Architecture

StintLab is built around a separation between the telemetry layer and the desktop application.


                    Racing Simulator
                           |
                           | Telemetry
                           v
                  +-------------------+
                  | Telemetry Service  |
                  |                   |
                  | UDP / Processing  |
                  +---------+---------+
                            |
                         WebSocket
                            |
                            v
                  +-------------------+
                  |   StintLab App    |
                  |                   |
                  | Electron / UI     |
                  +---------+---------+
                            |
               +------------+------------+
               |            |            |
               v            v            v
           Telemetry    Strategy     Pit Wall
             Views        Tools       Interface


The telemetry service is intended to act as a common layer between individual simulators and the StintLab interface.

This makes it possible to add new simulators without rebuilding the entire application around a single telemetry source.



## Technology

### Application

* Electron
* JavaScript
* HTML / CSS

### Telemetry

* Python
* UDP
* WebSocket

### Development

* Git
* GitHub
* VS Code

The technology stack may evolve as the project grows.



## Development Status

StintLab is **not yet a finished or production-ready application**.

The project is currently being developed and tested primarily around GT7 telemetry.

Some features shown in the roadmap are planned rather than implemented, and the application may change significantly as the architecture develops.

At the current stage, the project is primarily focused on:

1. Establishing a reliable telemetry pipeline
2. Validating telemetry data
3. Building the application architecture
4. Developing the first race-engineering interfaces
5. Preparing the architecture for additional racing platforms



## Vision

The long-term goal of StintLab is to become a **sim-racing race engineering platform** rather than simply another telemetry overlay.

The idea is to provide the driver and team with the information needed to make decisions during a race:

> **What is happening?**
> **Why is it happening?**
> **What should we do next?**

The project is being built with future multi-platform support in mind, while keeping the initial implementation focused on GT7.



## Screenshots

*Screenshots will be added as the interface develops.*



## Contributing

StintLab is currently a personal project and is still undergoing significant architectural changes.

Contributions, ideas and technical feedback may become more relevant as the project reaches a more stable stage.



## Disclaimer

StintLab is an independent project and is **not affiliated with or endorsed by Polyphony Digital, Sony Interactive Entertainment, Gran Turismo, or any other racing simulator/platform referenced by the project.**

All trademarks belong to their respective owners.



## Project Status

**StintLab is a work in progress.**

The current focus is building a reliable GT7 telemetry foundation that can eventually support a broader multi-platform motorsport engineering system.

