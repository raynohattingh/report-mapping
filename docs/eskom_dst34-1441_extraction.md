# DST 34-1441 Rev 1 (2013) — Full extraction for product design

Source: full PDF obtained by Rayno 2026-07-07 (02_Validation context: IAS call). This is the 2013 revision — superseded by 240-138196972; treat as structural skeleton, not current spec. **Note: Annex B ("Example of line inspection sheet") is missing from this copy — page 21 is blank apart from the title. The report-sheet exemplar remains unseen.**

## Governing context
- Aligns to NRS 082 + OHS Act. Cancels/replaces: BFN 002, BFN 032, BFN 0033, CEMS 0077, JHB Power Line Inspection Report, SCSASAAV2, DST0030.
- Inspection planning per DST_34-1456. Wooden-pole visual per DST_34-334. Pole-top per DGL_34-555 (DISAGABF5). Vegetation per servitude standards.
- Records flow (§5): Work order (job plan + task manual) → inspection/maintenance report = record of work → returned to Plant Department + Work Management Centre with work order; copy to Technical Services Centre. (Modern equivalent: SAP/CMMS defect records per 240-145514226.)

## Inspection regime (§4.3, Table 1)
| Type | Visual (4.3.1) | Detailed hands-on (4.3.2) | After handover (4.3.3) |
|---|---|---|---|
| Sub-transmission | Annually* | 10 years | Within 10 months |
| Distribution | Annually* | 10 years | Within 10 months |

*or after a close succession of unexplained faults. Frequencies default when no RCM study exists. Earth tests (Table 2): transformer/recloser/tower footing/SWER isolation — 5 years.

## Visual defect taxonomy (§4.3.1) — target classes for the vision/thermal pipeline
Broken insulators and arresters · pollution (record type: industrial / marine / sand / bird) · dampers/spacers adrift or faulty · erosion · discolouration/corrosion of conductors and steel towers · damaged conductors · incorrect ground/tree clearance · incorrect clearance on shared structures · incorrect Telkom-crossing clearance · activities under lines (buildings/encroachment) · worn hardware, damaged structures · oil/SF6 leaks on reclosers/sectionalizers/transformers · ENS single-line-diagram vs physical mismatch.

## Detailed inspection scope (§4.3.2)
- Towers: all hardware; corrosion (coastal/pollution priority); paintwork + foundations; pole numbering; bolts/dampers/connectors. Sampling: >100 structures → dismantle 1 suspension unit per 100, 1 damper+spacer per 50; <100 structures → at least one of each. Pole-top inspection per DGL_34-555.
- Steel/concrete poles: same categories minus sampling.
- Wooden poles: pole-by-pole condition incl. partial excavation (every pole in suspect areas, else every 10th), visual per DST_34-334, pole-top incl. earth bonding.

## Annex C checklist — the works-order pro forma (pages 22–25, fully extracted)
Structure: per-tower matrix (tower number columns) × numbered check items, Remarks column, INSPECTED BY / DATE header, SELF-SUPPORTING vs GUYED classification. Category-letter + item-number = implicit defect coding (A1…F12):

**A. Tower/Mast** (structural steel, corrosion; masts/beams/cross-arms/footings/plates-bolts/members)
Galvanizing: 1 reddish/whitish discoloration · 2 whole vs partial rust · 3 corroded away · 4 rust streaking off bolts · 5 galvanizing sandblasted. Foundations: 7 subsiding · 8 erosion at footing · 9 erosion approaching tower · 10 concrete 150mm above ground · 11 sand/soil over concrete · 12 hairline cracks on footing/benching. Members: 13 loose members (rubber-mallet bolt-ring test) · 14 missing members · 15 bottom members bent/damaged · 16 loose step bolts. Paint: 17 blistering · 18 peeling.

**B. Earthing:** 1 bolted tightly · 2 bolt rusting · 3 metal corroding where earth strap enters ground (remove soil).

**C. Stays/Guys:** 1 guy/cross-head housing or U-bolt rusting · 2 visible slip between guy wire and preformed rods · 3 tamper guards in place · 4 cut guy end strand lengths · 5 bitumen present/rust · 6 guy wire slack (wind/leeward note). Tension by dynamometer: 22dia >3,5t; 24dia >4,3t; 28dia >6t; 32dia >7,5t.

**D. Insulators:** 1 dirty · 2 bird dirt · 3 pollution · 4 broken · 5 number broken per string + position · 6 faulting on insulators · 7 security clips missing · 8 wasting/corrosion/pollution/erosion at pins/stems/rods · 9 hardware discolouration · 10 insulator type code: A=Porcelain, B=Glass, C=Cycloaliphatic, D=Composites. (Strain towers indicated vs self-supporting.)

**E. Conductors & Earth Wire:** 1 suspension clamp wear · 2 damper/spacer distorted · 3 loose wires/bird-caging · 4 wire bulging · 5 white powder on conductor · 6 conductor wearing · 7 burn marks · 8 bundle twisted · 9 hardware wearing (binoculars) · 10 conductor pulling through AGS clamp halves · 11 heat discolouration at mid-span joints/strain clamps/dampers · 12 railway within ±800m · 13 insulation on earth wires · 14 loose clamp bolts · 15 Crosby clamp in place on jumper · 16 dampers moved along span · 17 armour-rod damage.

**F. General:** 1 tower numbered · 2 number peeling · 3 number clear · 4 anti-climbing device damaged · 5 anti-climb obstruction free · 6 service road obstruction free · 7 access road wash-aways · 8 retaining wall damaged · 9 trees growing toward phases · 10 locks in place · 11 gate damage · 12 access difficult / helicopter required / new roads or quarries (remarks).

## What this standard does NOT contain (design-blocking gaps)
1. **No thermographic criteria at all** — no temperature-rise classes, emissivity rules, thermal severity thresholds. Dexter: the Eskom requirements are "mostly on the thermal side." The thermal spec lives elsewhere and we have zero pages of it.
2. **No Annexure H** — annexes run A–C in this revision; the H artifact (and the defect coding classification as Dexter named it) is in the current 240- doc set or contract packs.
3. **No transmission (275kV+) coverage** — separate standards family, still unseen.
4. **No data-format prescription** — nothing on digital submission, SAP defect record fields, or file formats; §5 predates the current CMMS workflow.
5. **Annex B report exemplar missing from this copy.**
