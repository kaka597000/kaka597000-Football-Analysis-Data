> ## Documentation Index
> Fetch the complete documentation index at: https://docs.therundown.io/llms.txt
> Use this file to discover all available pages before exploring further.

# V2: Get events by sport and date

> Retrieve events and markets for one sport and date. Review UTC offsets, market and book filters, scores-only requests and closed-price options.

## Endpoint details

Returns events with full market/odds data for the specified sport and date. This is the primary endpoint for building odds screens.

`main_line=true` also excludes closed prices while selecting main lines.

For known zero-delay access, this response's positive whole-integer `meta.delta_last_id` can bootstrap `/api/v2/markets/delta` only when this response explicitly reports `X-Data-Delay-Seconds: 0`. If that header is positive, absent, or invalid, use scoped snapshots instead; do not start market-delta polling with `0`.

### Scores-only discovery

Set `affiliate_ids=0` to retain events, scores and status without markets or price objects, including events without markets. Select an exact event, discover its markets with `GET /api/v2/events/{eventID}/markets`, then request prices from `GET /api/v2/events/{eventID}` with the desired market and sportsbook filters.

Review `offset` when selecting a date. For open main-line prices, set `main_line=true`; use `hide_closed=true` to exclude closed prices in other line views. Both flags default to `false`.


## OpenAPI

````yaml openapi.yaml GET /api/v2/sports/{sportID}/events/{date}
openapi: 3.1.0
info:
  title: TheRundown Sports API
  version: 2.0.0
  description: >
    **Resolve the event first.** Ambiguous date, team, player, or timezone? The
    agent asks instead of guessing.


    **Every price carries evidence.** Event, market, affiliate ID, line, and the
    price update time. A fetch time is not freshness.


    **Missing stays missing.** No remembered odds, no synthetic prices, no
    filled gaps.


    **IDs come from the API.** Sports, markets, and affiliates are discovered at
    runtime. Retired affiliates stay out.


    Real-time and historical sports data API: odds, lines, scores and statistics
    across major North American and international sports leagues.


    ## Authentication

    All endpoints (except `/sports` and `/affiliates`) require authentication.
    Send your API key from a private server-side environment variable in the
    `X-TheRundown-Key` header.

    The query-key security scheme is retained for compatibility with existing
    integrations and deprecated for new integrations; do not put keys in URLs,
    prompts, browser bundles, or public code.

    ## Off-the-Board Sentinel Value

    The value **0.0001** indicates a line is "off the board": the sportsbook has
    temporarily removed pricing (e.g., pending injury news). This is NOT an
    error. Display as "Off Board" or "N/A" in your UI.


    ## Rate Limiting

    Requests are rate-limited per API key tier. Check response headers for
    current limits.


    ## Data Updates

    - Live odds update in real-time during games

    - Use delta endpoints for efficient polling of changes

    - WebSocket connections available for streaming updates


    ## V1 vs V2

    V2 endpoints use market-based data structures (market_id, participants, line
    prices). V1 endpoints use legacy line-based structures (moneyline, spread,
    total objects). V2 is recommended for new integrations.
  contact:
    name: TheRundown API Support
    url: https://therundown.io
    email: support@therundown.io
  termsOfService: https://therundown.io/terms
servers:
  - url: https://therundown.io
    description: Production
security:
  - ApiKeyHeader: []
tags:
  - name: V2 Sports
    description: Sport listings, dates, and teams (V2)
  - name: V2 Events
    description: Events with market-based odds (V2)
  - name: V2 Markets
    description: Market definitions, odds, deltas, and history (V2)
  - name: V2 Futures
    description: >-
      Futures/outright competition events: championship and tournament-winner
      boards (V2, early access)
  - name: V2 Teams
    description: Team data, players, and stats (V2)
  - name: V2 Players
    description: Player data (V2)
  - name: V2 Stats
    description: Team and player statistics (V2)
  - name: V2 WebSocket
    description: Real-time streaming via WebSocket (V2)
  - name: V2 Reference
    description: 'Reference data: affiliates, sportsbooks, season types (V2)'
  - name: V1 Events
    description: Events with line-based odds (V1 legacy)
  - name: V1 Lines
    description: Moneyline, spread, total, best-line endpoints (V1 legacy)
  - name: V1 Sports
    description: Sport listings, dates, events, schedules (V1 legacy)
  - name: V1 Delta
    description: Delta/change feeds (V1 legacy)
  - name: V1 Reference
    description: Reference data (V1 legacy)
  - name: V1 WebSocket
    description: Real-time streaming via WebSocket (V1 legacy)
externalDocs:
  description: Build with AI guide
  url: https://therundown.io/build-with-ai
paths:
  /api/v2/sports/{sportID}/events/{date}:
    get:
      tags:
        - V2 Events
      summary: Get events with markets for a sport and date
      description: >
        Returns events with full market/odds data for the specified sport and
        date. This is the primary endpoint for building odds screens.


        `main_line=true` also excludes closed prices while selecting main lines.


        For known zero-delay access, this response's positive whole-integer
        `meta.delta_last_id` can bootstrap `/api/v2/markets/delta` only when
        this response explicitly reports `X-Data-Delay-Seconds: 0`. If that
        header is positive, absent, or invalid, use scoped snapshots instead; do
        not start market-delta polling with `0`.
      operationId: v2GetEventsBySportAndDate
      parameters:
        - $ref: '#/components/parameters/SportIDPath'
        - name: date
          in: path
          required: true
          schema:
            type: string
            format: date
            example: '2026-01-15'
        - $ref: '#/components/parameters/OffsetQuery'
        - $ref: '#/components/parameters/MarketIDsQuery'
        - $ref: '#/components/parameters/ParticipantIDsQuery'
        - $ref: '#/components/parameters/ParticipantTypeQuery'
        - $ref: '#/components/parameters/AffiliateIDsQuery'
        - $ref: '#/components/parameters/MainLineQuery'
        - $ref: '#/components/parameters/HideClosedQuery'
        - name: hide_no_markets
          in: query
          schema:
            type: string
            enum:
              - 'true'
              - 'false'
            default: 'false'
          description: Hide events with no market data
        - $ref: '#/components/parameters/EventStatusQuery'
        - name: exclude_status
          in: query
          schema:
            type: string
          description: Comma-separated event status strings to exclude
      responses:
        '200':
          description: Events with markets
          headers:
            X-Data-Delay-Seconds:
              description: >-
                Optional data-delay entitlement value in whole seconds. Only an
                explicit value of `0` confirms zero-delay access for
                market-delta bootstrap; a positive or missing value means use
                scoped snapshots.
              schema:
                type: integer
                minimum: 0
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/EventsV2Response'
              example:
                meta:
                  delta_last_id: '193500000'
                events:
                  - event_id: ada1bad2588972bb0f0e4debf9ed92b5
                    sport_id: 4
                    event_uuid: 11f2-1f6d-22f0a800-8cca-2165a45d5e4a
                    event_date: '2027-02-03T01:00:00Z'
                    score:
                      event_status: STATUS_SCHEDULED
                      score_away: 0
                      score_home: 0
                      game_period: 0
                      game_clock: 0
                    teams:
                      - team_id: 23
                        name: Los Angeles
                        mascot: Lakers
                        abbreviation: LAL
                        record: 38-18
                        is_away: true
                        is_home: false
                      - team_id: 1
                        name: Boston
                        mascot: Celtics
                        abbreviation: BOS
                        record: 42-14
                        is_away: false
                        is_home: true
                    schedule:
                      event_name: Los Angeles Lakers at Boston Celtics
                      season_type: Regular Season
                      season_year: 2026
                    markets:
                      - market_id: 1
                        period_id: 0
                        name: moneyline
                        participants:
                          - id: 23
                            type: TYPE_TEAM
                            name: Los Angeles Lakers
                            lines:
                              - value: ''
                                prices:
                                  '19':
                                    price: 150
                                    is_main_line: true
                                    updated_at: '2027-02-02T23:30:00Z'
                                  '23':
                                    price: 155
                                    is_main_line: true
                                    updated_at: '2027-02-02T23:28:00Z'
                          - id: 1
                            type: TYPE_TEAM
                            name: Boston Celtics
                            lines:
                              - value: ''
                                prices:
                                  '19':
                                    price: -180
                                    is_main_line: true
                                    updated_at: '2027-02-02T23:30:00Z'
                                  '23':
                                    price: -185
                                    is_main_line: true
                                    updated_at: '2027-02-02T23:28:00Z'
                      - market_id: 2
                        period_id: 0
                        name: handicap
                        participants:
                          - id: 23
                            type: TYPE_TEAM
                            name: Los Angeles Lakers
                            lines:
                              - value: '4.5'
                                prices:
                                  '19':
                                    price: -110
                                    is_main_line: true
                                    updated_at: '2027-02-02T23:30:00Z'
                                  '23':
                                    price: -108
                                    is_main_line: true
                                    updated_at: '2027-02-02T23:28:00Z'
                          - id: 1
                            type: TYPE_TEAM
                            name: Boston Celtics
                            lines:
                              - value: '-4.5'
                                prices:
                                  '19':
                                    price: -110
                                    is_main_line: true
                                    updated_at: '2027-02-02T23:30:00Z'
                                  '23':
                                    price: -112
                                    is_main_line: true
                                    updated_at: '2027-02-02T23:28:00Z'
                      - market_id: 3
                        period_id: 0
                        name: totals
                        participants:
                          - id: 1001
                            type: TYPE_RESULT
                            name: Over
                            lines:
                              - value: '224.5'
                                prices:
                                  '19':
                                    price: -110
                                    is_main_line: true
                                    updated_at: '2027-02-02T23:30:00Z'
                          - id: 1002
                            type: TYPE_RESULT
                            name: Under
                            lines:
                              - value: '224.5'
                                prices:
                                  '19':
                                    price: -110
                                    is_main_line: true
                                    updated_at: '2027-02-02T23:30:00Z'
components:
  parameters:
    SportIDPath:
      name: sportID
      in: path
      required: true
      schema:
        type: integer
      description: >
        Sport ID. Common values: 1=NCAAF, 2=NFL, 3=MLB, 4=NBA, 5=NCAAB, 6=NHL,
        7=UFC, 8=WNBA, 9=CFL, 10=MLS, 11=EPL, 16=UEFA Champions League, 17=UEFA
        Europa League (listed as UEFAEURO; 33 returns no events), 34=Liga MX,
        38=ATP Tennis, 39=WTA Tennis, 40=PGA Tour Golf, 41=Formula 1
    OffsetQuery:
      name: offset
      in: query
      schema:
        type: integer
        default: 0
        example: 300
      description: >-
        UTC offset in **minutes** for the date boundary. US zone values change
        with daylight saving time (daylight / standard), so use the value in
        effect on the date you request. Eastern `240` / `300`, Central `300` /
        `360`, Mountain `360` / `420`, Pacific `420` / `480`. Without this, the
        API day boundary is midnight UTC.
    MarketIDsQuery:
      name: market_ids
      in: query
      schema:
        type: string
        default: 1,2,3
      description: >
        Comma-separated market IDs. Defaults to `1,2,3` (Moneyline, Spread,
        Total); for soccer leagues and NHL the default is `1,2,3,563`. The
        soccer 3-way moneyline (home/draw/away) is served on market 1 as three
        participants; market 563 carries the NHL 60-minute regulation-time line.

        **Limit: 12 market IDs per request.** Requests with more than 12 IDs are
        rejected with a `400`: split larger requests into batches of 12, or omit
        the parameter to use the default.

        On market-definition endpoints (`/api/v2/events/{eventID}/markets`,
        `/api/v2/sports/{sportID}/markets/{date}`), omitting `market_ids`
        returns all available market definitions instead of the default set.

        Common IDs: 1=Moneyline, 2=Spread, 3=Total, 29=Player Points, 35=Player
        Rebounds, 38=Three Pointers, 39=Player Assists, 93=Player PRA, 94=Team
        Totals.

        Live variants: 41=Live ML, 42=Live Spread, 43=Live Total.
    ParticipantIDsQuery:
      name: participant_ids
      in: query
      schema:
        type: string
      description: Comma-separated participant IDs to filter (max 99)
    ParticipantTypeQuery:
      name: participant_type
      in: query
      schema:
        type: string
        enum:
          - TYPE_TEAM
          - TYPE_PLAYER
          - TYPE_RESULT
      description: Filter participants by type
    AffiliateIDsQuery:
      name: affiliate_ids
      in: query
      schema:
        type: string
      description: >
        Comma-separated sportsbook/affiliate IDs to filter. Common values
        include DraftKings (19), FanDuel (23), BetMGM (22), BookMaker (7),
        BetCRIS (9), Pinnacle (3), Polymarket US (31), Circa Sports (32), Bet105
        (33), and Heritage Sports (34). Availability varies by sport and market.

        On V2 event endpoints (`/api/v2/sports/{sportID}/events/{date}`,
        `/api/v2/events/{eventID}`, and their openers/closing siblings),
        `affiliate_ids=0` is a scores-only sentinel: the response keeps events,
        scores, and status and omits markets and price objects. Other endpoints
        that share this parameter treat `affiliate_ids` as a sportsbook filter
        only.
    MainLineQuery:
      name: main_line
      in: query
      schema:
        type: string
        enum:
          - 'true'
          - 'false'
        default: 'false'
      description: >-
        Only return main lines (primary odds, not alternates). On opening and
        closing endpoints, this selects main lines in the snapshot. Use history
        to follow which line was main at each timestamp.
    HideClosedQuery:
      name: hide_closed
      in: query
      schema:
        type: string
        enum:
          - 'true'
          - 'false'
        default: 'false'
      description: >-
        Exclude currently closed lines when `true`. Omit or set `false` to
        retrieve completed historical snapshots; an event can remain when no
        prices match.
    EventStatusQuery:
      name: event_status
      in: query
      schema:
        type: string
      description: >-
        Comma-separated event status strings to include (e.g.
        `STATUS_IN_PROGRESS,STATUS_HALFTIME`). Applied before `exclude_status`.
  schemas:
    EventsV2Response:
      type: object
      properties:
        meta:
          $ref: '#/components/schemas/EventsSnapshotMeta'
        events:
          type: array
          items:
            $ref: '#/components/schemas/EventV2'
    EventsSnapshotMeta:
      type: object
      nullable: true
      properties:
        delta_last_id:
          $ref: '#/components/schemas/MarketDeltaCursor'
    EventV2:
      type: object
      properties:
        event_id:
          type: string
          description: >-
            Canonical event identifier string used by V2 endpoints, filters, and
            delta feeds.
          example: ada1bad2588972bb0f0e4debf9ed92b5
        event_uuid:
          type: string
          description: >-
            Compatibility identifier retained for older integrations. Do not
            assume it matches `event_id`.
          example: 11f2-1f6d-22f0a800-8cca-2165a45d5e4a
        sport_id:
          type: integer
          example: 4
        event_date:
          type: string
          format: date-time
        rotation_number_away:
          type: integer
        rotation_number_home:
          type: integer
        score:
          $ref: '#/components/schemas/Score'
        teams:
          type: array
          items:
            $ref: '#/components/schemas/TeamNormalized'
        schedule:
          $ref: '#/components/schemas/Schedule'
        pitcher_away:
          $ref: '#/components/schemas/Pitcher'
        pitcher_home:
          $ref: '#/components/schemas/Pitcher'
        markets:
          type: array
          items:
            $ref: '#/components/schemas/MarketResponse'
        live_game_state:
          $ref: '#/components/schemas/LiveGameState'
        affiliate_source_ids:
          type: object
          additionalProperties:
            type: string
          description: >-
            Map of affiliate ID (as a string) to that sportsbook's own
            identifier for this event, when available. Useful for deep-linking
            or joining against a book's data. For Polymarket (affiliate 26) the
            value is the Polymarket event slug; see the Source identifiers
            section of the Sportsbook reference.
          example:
            '19': '31580014'
            '23': 34031-88749503
        teams_normalized:
          type: array
          description: >-
            The same team objects as `teams`, repeated under the V1 field name
            for V1-to-V2 migration parity.
          items:
            $ref: '#/components/schemas/TeamNormalized'
        affiliate_deep_links:
          type: object
          additionalProperties:
            type: string
          description: >-
            Navigation URLs keyed by affiliate ID (as a string). Each URL is the
            event's page on that sportsbook unless `affiliate_deep_link_types`
            marks it as a catalog fallback. Omitted when no links are available.
        affiliate_deep_link_types:
          type: object
          additionalProperties:
            type: string
            enum:
              - catalog
          description: >-
            Route type for entries in `affiliate_deep_links`, keyed by affiliate
            ID. `catalog` marks a validated sportsbook catalog page used as a
            fallback; an affiliate ID absent from this map has an event-page
            URL.
    MarketDeltaCursor:
      description: >-
        Positive whole-integer cursor for `/api/v2/markets/delta`. The API may
        return it as an integer or a numeric string. Use a snapshot value to
        begin market-delta polling only for known zero-delay access when that
        snapshot explicitly reports `X-Data-Delay-Seconds: 0`; otherwise use
        scoped snapshots and never substitute `0`.
      oneOf:
        - type: integer
          format: int64
          minimum: 1
        - type: string
          pattern: ^[1-9][0-9]*$
    Score:
      type: object
      properties:
        event_id:
          type: string
        event_status:
          type: string
          description: >
            Event status. Common values: STATUS_SCHEDULED, STATUS_IN_PROGRESS,
            STATUS_FINAL, STATUS_POSTPONED, STATUS_CANCELED, STATUS_SUSPENDED,
            STATUS_DELAYED, STATUS_RAIN_DELAY, STATUS_HALFTIME,
            STATUS_END_PERIOD, STATUS_END_OF_REGULATION, STATUS_OVERTIME,
            STATUS_FIRST_HALF, STATUS_SECOND_HALF
        team_id_away:
          type: integer
          description: Away team ID. Omitted when zero.
        team_id_home:
          type: integer
          description: Home team ID. Omitted when zero.
        score_away:
          type: integer
        score_home:
          type: integer
        winner_away:
          type: integer
        winner_home:
          type: integer
        score_away_by_period:
          type: array
          description: >-
            Away team's per-period scores, not running totals; index `0` is the
            first period. Overtime periods are appended. Read this array by its
            own length. Its sum is not guaranteed to equal `score_away`; verify
            before using it.
          items:
            type: integer
        score_home_by_period:
          type: array
          description: >-
            Home team's per-period scores, not running totals; index `0` is the
            first period. Overtime periods are appended. Read this array by its
            own length. Its sum is not guaranteed to equal `score_home`; verify
            before using it.
          items:
            type: integer
        venue_name:
          type: string
          description: Arena or stadium name. May be an empty string when unavailable.
        venue_location:
          type: string
          description: City and state. May be an empty string when unavailable.
        game_clock:
          type: integer
        display_clock:
          type: string
        is_clock_running:
          type: boolean
          description: Clock-running flag when supplied. Omitted when unavailable.
        game_period:
          type: integer
        broadcast:
          type: string
        event_status_detail:
          type: string
        updated_at:
          type: string
          format: date-time
    TeamNormalized:
      type: object
      properties:
        conference_id:
          type: integer
          description: >-
            Conference ID for the team, when it belongs to one. Omitted
            otherwise.
        division_id:
          type: integer
          description: Division ID for the team, when it belongs to one. Omitted otherwise.
        team_id:
          type: integer
        name:
          type: string
        mascot:
          type: string
        abbreviation:
          type: string
        record:
          type: string
        is_home:
          type: boolean
        is_away:
          type: boolean
        ranking:
          type: integer
          nullable: true
        conference:
          $ref: '#/components/schemas/Conference'
        division:
          $ref: '#/components/schemas/Division'
    Schedule:
      type: object
      properties:
        season_type:
          type: string
          example: Regular Season
        season_year:
          type: integer
          example: 2026
        conference_competition:
          type: boolean
          nullable: true
        conference_name:
          type: string
        league_name:
          type: string
          nullable: true
        event_name:
          type: string
        attendance:
          type: string
        event_headline:
          type: string
        game_number:
          type: integer
          enum:
            - 1
            - 2
          description: >-
            Game number for a true MLB doubleheader. Omitted for ordinary and
            standalone makeup games.
        game_type:
          type: string
          enum:
            - doubleheader
            - makeup
            - doubleheader_makeup
          description: >-
            Structured MLB doubleheader or makeup classification. Omitted for
            ordinary games.
        week:
          type: integer
        week_name:
          type: string
        week_detail:
          type: string
    Pitcher:
      type: object
      properties:
        id:
          type: integer
        name:
          type: string
        throws_left_handed:
          type: boolean
          nullable: true
        throws_right_handed:
          type: boolean
          nullable: true
        bats_left_handed:
          type: boolean
          nullable: true
        bats_right_handed:
          type: boolean
          nullable: true
    MarketResponse:
      type: object
      description: Market with participants and prices for a specific event
      properties:
        id:
          type: integer
          format: int64
        market_id:
          type: integer
          example: 1
        period_id:
          type: integer
        name:
          type: string
          example: Money Line
        market_description:
          type: string
        participants:
          type: array
          items:
            $ref: '#/components/schemas/MarketParticipantResponse'
    LiveGameState:
      type: object
      description: >
        Real-time game-state snapshot embedded on live event payloads. Requires
        the live game state entitlement (Ultra plan or higher); keys without it
        never receive this field. Sport-specific blocks (`mlb`, `football`,
        `basketball`, `hockey`) are present only for the relevant sport.
      properties:
        event_id:
          type: string
        sport_id:
          type: integer
        sport:
          type: string
          description: >-
            Sport slug: `mlb`, `nba`, `nba-summer`, `ncaab`, `nfl`, `ncaaf`,
            `nhl`, `wnba`, or `soccer`
          example: mlb
        period:
          type: integer
          description: Current period/inning/quarter number
        half_indicator:
          type: string
          description: >-
            Half within the period where applicable (`top` or `bot` for MLB
            innings)
        display_clock:
          type: string
          description: Clock display string. Omitted when inapplicable or not yet known.
        clock_seconds:
          type: integer
          description: >-
            The same clock in seconds. Omitted when inapplicable or not yet
            known.
        clock_running:
          type: boolean
          description: >-
            Whether the clock has been observed running. Omitted when
            inapplicable or not yet known.
        clock_as_of:
          type: string
          format: date-time
          description: >-
            When this clock value was observed, separate from the state row's
            updated_at.
        last_play:
          $ref: '#/components/schemas/LastPlayRef'
        updated_at:
          type: string
          format: date-time
        mlb:
          type: object
          description: Baseball-only snapshot
          properties:
            balls:
              type: integer
            strikes:
              type: integer
            outs:
              type: integer
            on_first:
              $ref: '#/components/schemas/PlayPlayerSummary'
            on_second:
              $ref: '#/components/schemas/PlayPlayerSummary'
            on_third:
              $ref: '#/components/schemas/PlayPlayerSummary'
            current_batter:
              $ref: '#/components/schemas/PlayPlayerSummary'
            current_pitcher:
              $ref: '#/components/schemas/PlayPlayerSummary'
        football:
          type: object
          description: NFL/NCAAF-only snapshot
          properties:
            possession_team_id:
              type: integer
            down:
              type: integer
            distance:
              type: integer
            yard_line:
              type: integer
            down_distance_text:
              type: string
              example: 3rd & 4 at KC 38
            short_down_distance_text:
              type: string
              example: 3rd & 4
            possession_text:
              type: string
            is_red_zone:
              type: boolean
            home_timeouts:
              type: integer
            away_timeouts:
              type: integer
        basketball:
          type: object
          description: NBA/WNBA/NCAAB-only snapshot
          properties:
            possession_team_id:
              type: integer
            home_timeouts:
              type: integer
            away_timeouts:
              type: integer
            home_in_bonus:
              type: boolean
            away_in_bonus:
              type: boolean
        hockey:
          type: object
          description: NHL-only snapshot
          properties:
            possession_team_id:
              type: integer
            strength:
              type: string
              description: Skater strength situation (e.g. even strength, power play)
            power_play_team_id:
              type: integer
            home_shots_on_goal:
              type: integer
            away_shots_on_goal:
              type: integer
            home_goalie_pulled:
              type: boolean
            away_goalie_pulled:
              type: boolean
    Conference:
      type: object
      properties:
        conference_id:
          type: integer
        division_id:
          type: integer
          description: >-
            Division the conference belongs to, when set (for example `1`, FBS,
            in NCAA Football). Omitted otherwise.
        sport_id:
          type: integer
        name:
          type: string
    Division:
      type: object
      properties:
        division_id:
          type: integer
        conference_id:
          type: integer
        sport_id:
          type: integer
        name:
          type: string
    MarketParticipantResponse:
      type: object
      properties:
        id:
          type: integer
          description: >-
            Stable, joinable participant identifier. Join on this field rather
            than name to avoid shared-name collisions. Its meaning depends on
            `type`: for `TYPE_TEAM` it is the normalized team ID (stable across
            seasons, matches `event.teams[].team_id`; full record at GET
            /api/v2/teams/{team_id}); for `TYPE_PLAYER` it is the player ID
            (full record at GET /api/v2/players/{player_id}); for `TYPE_RESULT`
            it is a small outcome index (e.g. 0/1 for Over/Under) and is not a
            team or player resource key.
          example: 51
        type:
          type: string
          description: >-
            Kind of participant. Determines what `id` points to (team, player,
            or result outcome).
          enum:
            - TYPE_TEAM
            - TYPE_PLAYER
            - TYPE_RESULT
        name:
          type: string
          description: >-
            Display name. Not guaranteed unique across participants: join on
            `id`, not `name`.
          example: New England Patriots
        lines:
          type: array
          items:
            $ref: '#/components/schemas/MarketLinesResponse'
    LastPlayRef:
      type: object
      description: >-
        Reference to the most recent play, mirrored from the play-by-play
        timeline
      properties:
        display_clock:
          type: string
          description: >-
            Game clock at the moment of the play, frozen thereafter. The live
            clock is `display_clock` on `live_game_state`.
        play_id:
          type: integer
          format: int64
        sequence:
          type: integer
        type:
          type: string
        result:
          type: string
        description:
          type: string
        team_id:
          type: integer
        scoring_play:
          type: boolean
        score_value:
          type: integer
        occurred_at:
          type: string
          format: date-time
        participants:
          type: array
          items:
            $ref: '#/components/schemas/PlayParticipant'
    PlayPlayerSummary:
      type: object
      properties:
        player_id:
          type: integer
          format: int64
        name:
          type: string
        team_id:
          type: integer
    MarketLinesResponse:
      type: object
      properties:
        id:
          type: string
        value:
          type: string
          description: >-
            Line value. For spreads/totals this is numeric; for some prop and
            special markets it can be a method, round, threshold, or other
            display value. When `line_value_is_participant` is true, the
            participant usually carries the selection.
        selection:
          type: string
        handicap:
          type: string
        prices:
          type: object
          description: Prices keyed by affiliate ID
          additionalProperties:
            $ref: '#/components/schemas/MarketLinePriceResponse'
    PlayParticipant:
      type: object
      properties:
        player_id:
          type: integer
          format: int64
          description: 'Normalized player ID: joins to the players endpoints'
        name:
          type: string
        team_id:
          type: integer
        role:
          type: string
          example: batter
        position:
          type: string
    MarketLinePriceResponse:
      type: object
      properties:
        id:
          type: string
        price:
          type: number
          description: American odds price. Value of 0.0001 means "off the board".
          example: -110
        price_delta:
          type: number
          nullable: true
          description: Change from previous price
        is_main_line:
          type: boolean
          description: Whether this is the primary/main line
        source_id:
          type: string
          description: >-
            The sportsbook's own identifier for this price/selection, when
            available. Omitted when the book does not expose one. For Polymarket
            (affiliate 26) this encodes
            `<event-slug>-<gamma-market-id>-<clob-token-id>` (parse from the
            right; the two trailing fields are numeric); see the Source
            identifiers section of the Sportsbook reference for the full mapping
            recipe.
        deep_link:
          type: string
          description: >-
            Link to this exact selection on the sportsbook, on books that
            support it (for example BetMGM and Kalshi). Omitted when no exact
            link is available.
        liquidity_usd:
          type: number
          description: >-
            USD reading for this price. On Kalshi (affiliate 25) and Polymarket
            (affiliate 26) this is approximate resting order-book depth
            (Polymarket reports its own figure alongside the price; Kalshi's is
            derived from its order book on a separate refresh cadence). On
            Pinnacle (affiliate 3) this is the book's max stake. Novig
            (affiliate 30) and Polymarket US (affiliate 31) prices also carry a
            reading. Omitted entirely, never null and never a fabricated 0, when
            a current reading is not available. See the docs FAQ for details.
          example: 4210.5
        updated_at:
          type: string
          format: date-time
        closed_at:
          type: string
          format: date-time
          description: >-
            Closing timestamp for a closed current price. Omitted while open;
            when applying a full price object, absence means open and clears any
            previously stored closure timestamp.
  securitySchemes:
    ApiKeyHeader:
      type: apiKey
      in: header
      name: X-TheRundown-Key
      description: Recommended API key request header for new integrations

````

This documentation is built and hosted on [Mintlify](https://mintlify.com), a developer documentation platform.