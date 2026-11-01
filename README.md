# TA CoE Sender

Home-Assistant-Integration, die Werte aus Home Assistant per **CoE (CAN over Ethernet, UDP)** an eine
Technische-Alternative-**C.M.I.** schickt. Die C.M.I. stellt sie als Ausgänge eines virtuellen CAN-Knotens
auf den CAN-Bus, sodass eine UVR16x2 (oder ein anderer TA-Regler) sie als normalen CAN-Eingang lesen kann.

Die Integration kann nur **senden**. Zum Lesen von der C.M.I. gibt es
[DeerMaximum/Technische-Alternative-CoE](https://github.com/DeerMaximum/Technische-Alternative-CoE).
Beide laufen nebeneinander, sofern sie unterschiedliche CAN-Knotennummern nutzen.
Diese Integration braucht kein Addon, nur UDP von Home Assistant zur C.M.I.

## Installation

**HACS:** In HACS unter *Benutzerdefinierte Repositories* die Adresse
`https://github.com/nilseckert/ha-ta-coe-sender` mit Typ *Integration* hinzufügen und installieren.

**Manuell:** Den Ordner `custom_components/ta_coe_sender` nach `<config>/custom_components/` kopieren
(bei Docker in das gemountete Config-Verzeichnis). Home Assistant neu starten.

Danach: *Einstellungen → Geräte & Dienste → Integration hinzufügen → TA CoE Sender*.

## Einrichtung

1. **Integration anlegen:** IP der C.M.I., CoE-Version und eine **eigene CAN-Knotennummer** (1–62) wählen.
   Die Nummer muss im CAN-Bus frei sein. Der UDP-Port bleibt leer (V1: 5441, V2: 5442).
2. **Werte zuordnen:** In der Integration auf *Konfigurieren → Wert hinzufügen*: Entität, analog oder digital,
   Ausgangsnummer, bei analog Einheit und Dezimalstellen.
3. **C.M.I.:** Die C.M.I. muss Pakete von Home Assistant als CoE-Quelle annehmen (IP und Knotennummer
   von Home Assistant). Wo das in deiner Firmware eingestellt wird, hängt von der Version ab, siehe
   [FHEM-Wiki: CanOverEthernet](https://wiki.fhem.de/wiki/CanOverEthernet) und das TA-Handbuch.
   Ob die Werte ankommen, siehst du in der C.M.I. (im openHAB-Forum wird dafür die Seite
   `http://<cmi-ip>/#status_coe.cgi` genannt).
4. **UVR (TAPPS2):** CAN-Eingang anlegen mit derselben **Knotennummer** und **Ausgangsnummer**
   wie hier gewählt, Messgröße passend zur Einheit.

## Verhalten

- Bei **jeder Zustandsänderung** werden alle zugeordneten Werte sofort gesendet, zusätzlich zyklisch
  (Standard 60 s, einstellbar). Das Intervall muss kürzer sein als der Timeout des CAN-Eingangs in der UVR.
- Werte, die gerade `unavailable` oder `unknown` sind, werden **nicht gesendet**. Der Timeout in der UVR
  läuft dann ab und der dort eingestellte Ersatzwert greift, statt dass ein alter Wert weiterläuft.
  Das gilt auch, wenn Home Assistant ausfällt.
- Analoge Werte werden als Ganzzahl `Wert × 10^Dezimalstellen` gesendet. Bei °C ist 1 Dezimalstelle
  voreingestellt (45,3 °C → 453). Bei allen anderen Einheiten musst du die Dezimalstellen aus der
  TA-Tabelle der Messgrößen selbst eintragen. CoE V1 erlaubt Werte von −32768 bis 32767, V2 deutlich mehr.
- Digitale Werte: `on`, `true` und `1` gelten als EIN, alles andere als AUS.
- V1: Ausgänge 1–32 (analog und digital getrennt gezählt). V2: 1–64.

## Was geprüft ist und was nicht

- Das Byte-Layout von V1 und V2 ist gegen den Quellcode von
  [python-can-coe 0.1.1](https://pypi.org/project/python-can-coe/) abgeglichen (1400 zufällige Pakete identisch).
- Config Flow, Options Flow und das Senden sind mit Home Assistant 2026.2.3 getestet,
  das Senden gegen einen simulierten UDP-Empfänger. `pytest` im Projektverzeichnis führt alles aus
  (benötigt `pytest-homeassistant-custom-component`).
- **Nicht** getestet: eine echte C.M.I./UVR. Besonders bei **CoE V2** ist unklar, ob die Skalierung je Einheit
  genauso wie bei V1 funktioniert (die DeerMaximum-README warnt vor Skalierungsfehlern bei V2).
  Für V2 gilt daher: erst mit einem Testwert prüfen.

## Fehlersuche

- Kommt in der C.M.I. nichts an: `tcpdump -n udp port 5441` (bzw. 5442) auf dem HA-Host zeigt, ob Pakete
  rausgehen. Mit `logger: logs: custom_components.ta_coe_sender: debug` siehst du jedes gesendete Paket als Hex.
- Firewall oder VLAN zwischen HA und C.M.I. prüfen.
- Falsche Größenordnung in der UVR: Dezimalstellen bzw. Einheit prüfen.

## Lizenz

MIT, siehe [LICENSE](LICENSE).
