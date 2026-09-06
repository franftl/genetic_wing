# UAV FP — Research Note 7: Fixed-Wing UAVs Using 18650-Style Li-ion Cells for Range

*Compiled 12 August 2026. Follow-up to Research Notes 1–6.*

## Short answer

Yes — this is an established practice at both ends of the spectrum: hobbyist/DIY long-range fixed-wing builds and at least one well-known commercial long-range fixed-wing UAV (Applied Aeronautics' Albatross) explicitly offer cylindrical Li-ion packs (the 18650/21700 family) as an upgrade specifically to extend flight time and range over standard LiPo. It's also a technically well-matched choice for fixed-wing specifically, more so than for multirotors, for reasons worth understanding rather than just copying.

## Why 18650-style cells help range, and why fixed-wing suits them particularly well

The core reason is energy density: cylindrical Li-ion cells store meaningfully more energy per unit weight than the pouch-style LiPo packs typical in most drones. Applied Aeronautics states this plainly for their own aircraft — **233 Wh/kg for their Li-ion option versus 145 Wh/kg for standard LiPo** — roughly a 60% improvement in energy stored per kilogram carried. A separate long-range FPV source puts it more bluntly: a 4S 18650 pack can carry roughly double the capacity of a similarly-weighted 4S LiPo pack.

The trade-off is discharge rate: Li-ion cells are typically only rated around 5C continuous discharge, versus roughly 50C for a performance LiPo — meaning Li-ion can't dump current nearly as fast. For a multirotor, which constantly fights gravity with high sustained current draw (and needs big current spikes for aggressive maneuvers), that's a real limitation. A fixed-wing aircraft, by contrast, gets most of its lift from the wing rather than the motor fighting gravity directly, so its cruise power draw is comparatively low and steady — a much better match for what Li-ion cells are good at. This is essentially why the practice concentrates specifically in the fixed-wing (and flying-wing) long-range community rather than being common on multirotors: the airframe's power profile happens to suit the battery chemistry's strength (energy density) while mostly avoiding its weakness (peak current).

## Concrete examples

**Applied Aeronautics Albatross** — a well-known commercial long-range fixed-wing UAV (sold ready-to-fly, marketed for long-range/BVLOS-type mapping and surveillance missions). Their standard configuration uses a 6S 8Ah LiPo pack (1.1 kg) for about 1 hour of flight; they offer a "custom Lithium Ion" battery option (~1.2 kg) that extends flight time to 90–120 minutes, explicitly attributing the gain to the 233 vs 145 Wh/kg energy density difference. This is a real product decision by an actual commercial UAV manufacturer, not just a hobbyist workaround.

**Skywalker X8 (and similar flying-wing airframes)** — a very popular, inexpensive fixed-wing/flying-wing platform in the long-range FPV community, frequently rebuilt around 18650 Li-ion packs specifically to stretch endurance. One documented build (DroneTrest forum) used a 6S6P pack of 36 Panasonic NCR18650GA cells — 21,000 mAh, 466 Wh, 22.2V nominal, rated 60A continuous — built specifically for a fixed-wing long-range drone; other builders in the same discussion reported using the same NCR18650GA cells in smaller 3S2P/4S2P packs for flying wings, describing them as running only "slightly warm" even at maximum discharge, which is a reasonable proxy for the cells being well within their comfort zone on this kind of airframe.

**Commercial mapping/survey battery vendors** now sell purpose-built long-endurance packs aimed at this exact use case (fixed-wing survey/mapping UAVs), offered in configurations like 6S 22,000 mAh up to 12S/14S packs around 28,000–30,000 mAh, marketed on endurance rather than peak power — consistent with the fixed-wing cruise-power profile described above. (Take the vendor-claimed energy density figures on these product pages, sometimes as high as 300–400 Wh/kg, with some skepticism — that's above what current commercial 18650/21700 cells typically achieve and reads like optimistic marketing rather than a verified spec; Applied Aeronautics' own stated 233 Wh/kg is a more grounded reference point.)

## Relevance to UAV FP

Given Research Note 5's point about needing meaningful range to cover dispersed onshore wells, and that a fixed-wing (or at least a hybrid VTOL/fixed-wing) airframe is a natural fit for that kind of point-to-point endurance mission versus a multirotor loitering over a single site — this is a legitimate, precedented way to extend your platform's range/endurance if the airframe choice leans fixed-wing, without needing exotic battery technology. Worth treating as a concrete design lever rather than a hypothetical: buy or hand-build an 18650/21700 pack sized to your airframe's cruise current draw, sized around the same kind of cell (Panasonic/Sony/Samsung 18650 or 21700 cells are the standard, well-documented choice in these builds) that shows up repeatedly in both the hobbyist and commercial examples above.

## Sources

- [Albatross FAQ — battery options and energy density figures (Applied Aeronautics)](https://www.appliedaeronautics.com/faq)
- [Using Li-ion Battery Packs for Long Range FPV Drone Flying (Oscar Liang)](https://oscarliang.com/li-ion-battery-long-range/)
- [Li-ion battery pack for a fixed-wing long-range drone — 6S6P 21000mAh (DroneTrest forum)](https://www.dronetrest.com/t/li-ion-battery-pack-for-a-fixed-wing-long-range-drone-6s6p-21000mah/7424)
- [Mapping Drone Battery for Long Endurance Survey UAV (XT Battery, commercial product page)](https://www.xtbattery.com/product/mapping-drone-battery-for-survey-uav/)
- [Applied Aeronautics Develops Long-Range Commercial Fixed-Wing UAV (Unmanned Systems Technology)](https://www.unmannedsystemstechnology.com/2018/12/applied-aeronautics-develops-fixed-wing-uavs-for-long-range-commercial-applications/)
