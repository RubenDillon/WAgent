# Form semantics

## Role vocabulary

| Role | Strong terms |
|---|---|
| origin | origin, from, departing from, leaving from, desde, origen |
| destination | destination, to, arriving at, flying to, hacia, destino |
| departure_date | departure date, depart, outbound, ida, partida |
| return_date | return date, return, inbound, regreso, vuelta |
| passengers | passengers, travelers, pax, guests, pasajeros, viajeros |
| adults | adult, adults, adulto, adultos |
| cabin | cabin, travel class, fare class, economy, cabina, clase |
| currency | currency, payment currency, pay in USD, USD, moneda |
| flight_search | search flights, find flights, book flight, buscar vuelos |
| site_search | search this site, help search, what can we help, buscar en el sitio |

Inspect `id`, `name`, `type`, `placeholder`, `aria-label`, `aria-labelledby`, linked label, nearby text, `autocomplete`, role, select options, `data-*`, min/max, checked, disabled, and current value.

A flight form normally contains origin + destination + departure date, and often return, passengers, cabin, and a flight-search submit. A single generic `Search` field is not evidence of a flight form.
