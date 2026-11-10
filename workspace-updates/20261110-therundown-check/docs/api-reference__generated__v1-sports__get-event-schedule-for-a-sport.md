> ## Documentation Index
> Fetch the complete documentation index at: https://docs.therundown.io/llms.txt
> Use this file to discover all available pages before exploring further.

# Get event schedule for a sport

> List scheduled events for one sport using the non-billable V1 schedule endpoint. Review date filters and usage-window response headers.

## Endpoint details

Returns scheduled events for a sport. This endpoint is non-billable:
every successful response, including nonempty ones, consumes zero data
points, so `X-Datapoints` is omitted. Usage window headers are still
returned for keys with an active plan.


## OpenAPI

````yaml openapi.yaml GET /api/v1/sports/{sportID}/schedule
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
  /api/v1/sports/{sportID}/schedule:
    get:
      tags:
        - V1 Sports
      summary: Get event schedule for a sport
      description: |
        Returns scheduled events for a sport. This endpoint is non-billable:
        every successful response, including nonempty ones, consumes zero data
        points, so `X-Datapoints` is omitted. Usage window headers are still
        returned for keys with an active plan.
      operationId: v1GetScheduleBySport
      parameters:
        - $ref: '#/components/parameters/SportIDPath'
        - name: limit
          in: query
          schema:
            type: integer
            default: 50
        - name: season_year
          in: query
          schema:
            type: integer
        - name: season_type_id
          in: query
          schema:
            type: integer
        - name: from
          in: query
          schema:
            type: string
            format: date
        - name: team_id
          in: query
          schema:
            type: integer
        - name: last_event_uuid
          in: query
          schema:
            type: string
          description: 'Cursor for pagination: pass the last event UUID from previous page'
        - name: sort
          in: query
          schema:
            type: string
            default: asc
            enum:
              - asc
              - desc
        - name: conference_id
          in: query
          schema:
            type: integer
        - name: division_id
          in: query
          schema:
            type: integer
        - name: include
          in: query
          schema:
            type: string
            enum:
              - teams
          description: >-
            Set to `teams` to add `away_team_detail` and `home_team_detail`
            objects to each schedule entry.
      responses:
        '200':
          description: Schedule
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ScheduleResponse'
              example:
                schedules:
                  - event_id: 09bfa53f8484a63e584398545c035932
                    event_uuid: 11f1-07a5-c61d4000-867b-48b2af0d735d
                    sport_id: 4
                    event_date: '2026-02-12T00:00:00Z'
                    league_name: National Basketball Association
                    season_type: Regular Season
                    season_year: 2026
                    event_name: Atlanta at Charlotte
                    teams_normalized:
                      - team_id: 11
                        name: Atlanta
                        mascot: Hawks
                        abbreviation: ATL
                        is_away: true
                        is_home: false
                      - team_id: 12
                        name: Charlotte
                        mascot: Hornets
                        abbreviation: CHA
                        is_away: false
                        is_home: true
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
  schemas:
    ScheduleResponse:
      type: object
      properties:
        schedules:
          type: array
          items:
            $ref: '#/components/schemas/ScheduledEvent'
    ScheduledEvent:
      type: object
      properties:
        id:
          type: string
          description: Schedule row identifier.
        event_id:
          type: string
        event_uuid:
          type: string
        sport_id:
          type: integer
        season_type:
          type: string
        season_year:
          type: integer
        away_team_id:
          type: integer
          description: Normalized team ID of the away team.
        home_team_id:
          type: integer
          description: Normalized team ID of the home team.
        away_team:
          type: string
        home_team:
          type: string
        date_event:
          type: string
          format: date-time
        neutral_site:
          type: boolean
          nullable: true
        conference_competition:
          type: boolean
          nullable: true
        league_name:
          type: string
          nullable: true
        away_score:
          type: integer
          nullable: true
        home_score:
          type: integer
          nullable: true
        winner_away:
          type: integer
          nullable: true
          description: Same as `winner_away` on the score object.
        winner_home:
          type: integer
          nullable: true
          description: Same as `winner_home` on the score object.
        headline:
          type: string
          description: Event headline, when available. Omitted otherwise.
        event_name:
          type: string
          nullable: true
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
        broadcast:
          type: string
          nullable: true
        event_location:
          type: string
          nullable: true
        attendance:
          type: integer
          nullable: true
        pitcher_home:
          $ref: '#/components/schemas/Pitcher'
        pitcher_away:
          $ref: '#/components/schemas/Pitcher'
        updated_at:
          type: string
          format: date-time
          description: Last update time of the event record. Omitted when unknown.
        event_status:
          type: string
          description: Event status, for example `STATUS_SCHEDULED`. Omitted when empty.
        event_status_detail:
          type: string
          description: Human-readable status detail. Omitted when empty.
        away_team_detail:
          $ref: '#/components/schemas/TeamNormalized'
        home_team_detail:
          $ref: '#/components/schemas/TeamNormalized'
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
  securitySchemes:
    ApiKeyHeader:
      type: apiKey
      in: header
      name: X-TheRundown-Key
      description: Recommended API key request header for new integrations

````

This documentation is built and hosted on [Mintlify](https://mintlify.com), a developer documentation platform.