# Go Web Server Design

**Date**: 2025-10-26
**Status**: [x] Approved
**Directory**: `src/webserver/`
**Purpose**: Serve BFI IMAX listings via HTML pages and RSS feeds

---

## Purpose

Provide web interface for BFI IMAX listings:
1. HTML page with all upcoming showings
2. RSS feeds (current schedule + daily changes)
3. Health endpoint for monitoring
4. Static file serving (CSS, JS, images)

**Technology**: Go (stdlib HTTP server, no framework)

---

## Architecture Overview

### Phase 1: Server-Rendered HTML (Initial)

```
┌─────────────┐
│   Browser   │
└──────┬──────┘
       │ HTTP GET /
       ↓
┌─────────────┐
│  Go Server  │
└──────┬──────┘
       │ SQL query
       ↓
┌─────────────┐
│   SQLite    │
└─────────────┘
```

**Flow**:
1. Browser requests `/`
2. Go server queries SQLite `upcoming_showings` view
3. Go server renders HTML template
4. Browser displays listing table

### Directory Structure

```
src/webserver/
├── main.go                 # Entry point
├── handlers/
│   ├── listings.go         # / endpoint
│   ├── rss.go              # /rss/* endpoints
│   ├── health.go           # /health endpoint
│   └── static.go           # /static/* files
├── db/
│   ├── db.go               # Database connection
│   └── queries.go          # SQL queries
├── models/
│   └── models.go           # Data structures
├── templates/
│   ├── base.html           # Base template
│   ├── listings.html       # Listings page
│   └── error.html          # Error page
├── static/
│   ├── css/
│   │   └── style.css
│   └── js/
│       └── app.js          # Future: client-side enhancements
└── config/
    └── config.go           # Configuration
```

---

## Implementation

### 1. Main Entry Point

```go
// main.go
package main

import (
    "context"
    "database/sql"
    "log"
    "net/http"
    "os"
    "os/signal"
    "syscall"
    "time"

    "webserver/config"
    "webserver/db"
    "webserver/handlers"

    _ "github.com/mattn/go-sqlite3"
)

func main() {
    // Load configuration
    cfg := config.Load()

    // Connect to database
    database, err := db.Connect(cfg.DBPath)
    if err != nil {
        log.Fatalf("Failed to connect to database: %v", err)
    }
    defer database.Close()

    // Validate database schema
    if err := db.ValidateSchema(database); err != nil {
        log.Fatalf("Database schema validation failed: %v", err)
    }

    // Setup HTTP handlers
    mux := http.NewServeMux()

    // Listings
    mux.HandleFunc("/", handlers.ListingsHandler(database))

    // RSS feeds
    mux.HandleFunc("/rss/current", handlers.CurrentRSSHandler(database))
    mux.HandleFunc("/rss/daily", handlers.DailyRSSHandler(database))

    // Health check
    mux.HandleFunc("/health", handlers.HealthHandler(database))

    // Static files
    staticFS := http.FileServer(http.Dir("./static"))
    mux.Handle("/static/", http.StripPrefix("/static/", staticFS))

    // Robots.txt (restrictive)
    mux.HandleFunc("/robots.txt", handlers.RobotsHandler)

    // Wrap with middleware
    handler := loggingMiddleware(mux)

    // Create server
    srv := &http.Server{
        Addr:         cfg.ListenAddr,
        Handler:      handler,
        ReadTimeout:  10 * time.Second,
        WriteTimeout: 10 * time.Second,
        IdleTimeout:  60 * time.Second,
    }

    // Start server in goroutine
    go func() {
        log.Printf("Server starting on %s", cfg.ListenAddr)
        if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
            log.Fatalf("Server error: %v", err)
        }
    }()

    // Wait for interrupt signal
    quit := make(chan os.Signal, 1)
    signal.Notify(quit, os.Interrupt, syscall.SIGTERM)
    <-quit

    log.Println("Server shutting down...")

    // Graceful shutdown
    ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
    defer cancel()

    if err := srv.Shutdown(ctx); err != nil {
        log.Fatalf("Server forced to shutdown: %v", err)
    }

    log.Println("Server stopped")
}

func loggingMiddleware(next http.Handler) http.Handler {
    return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        start := time.Now()
        next.ServeHTTP(w, r)
        log.Printf("%s %s %s", r.Method, r.RequestURI, time.Since(start))
    })
}
```

---

### 2. Configuration

```go
// config/config.go
package config

import (
    "os"
)

type Config struct {
    ListenAddr string
    DBPath     string
    LogLevel   string
    SiteTitle  string
    SiteURL    string
}

func Load() *Config {
    return &Config{
        ListenAddr: getEnv("LISTEN_ADDR", ":8080"),
        DBPath:     getEnv("DB_PATH", "/data/listing.db"),
        LogLevel:   getEnv("LOG_LEVEL", "info"),
        SiteTitle:  getEnv("SITE_TITLE", "BFI IMAX Listings"),
        SiteURL:    getEnv("SITE_URL", "http://localhost:8080"),
    }
}

func getEnv(key, defaultValue string) string {
    if value := os.Getenv(key); value != "" {
        return value
    }
    return defaultValue
}
```

---

### 3. Database Layer

```go
// db/db.go
package db

import (
    "database/sql"
    "fmt"

    _ "github.com/mattn/go-sqlite3"
)

func Connect(dbPath string) (*sql.DB, error) {
    db, err := sql.Open("sqlite3", dbPath)
    if err != nil {
        return nil, fmt.Errorf("failed to open database: %w", err)
    }

    // Set connection pool settings
    db.SetMaxOpenConns(25)
    db.SetMaxIdleConns(5)
    db.SetConnMaxLifetime(5 * time.Minute)

    // Test connection
    if err := db.Ping(); err != nil {
        return nil, fmt.Errorf("failed to ping database: %w", err)
    }

    return db, nil
}

func ValidateSchema(db *sql.DB) error {
    // Check required tables exist
    tables := []string{"listings", "scrape_schedule", "movie_runtimes"}

    for _, table := range tables {
        var name string
        query := "SELECT name FROM sqlite_master WHERE type='table' AND name=?"
        err := db.QueryRow(query, table).Scan(&name)
        if err == sql.ErrNoRows {
            return fmt.Errorf("required table missing: %s", table)
        }
        if err != nil {
            return fmt.Errorf("schema validation error: %w", err)
        }
    }

    return nil
}
```

```go
// db/queries.go
package db

import (
    "database/sql"
    "webserver/models"
)

func GetUpcomingShowings(db *sql.DB) ([]models.Showing, error) {
    query := `
        SELECT
            showing_date,
            showing_time,
            showing_datetime_utc,
            movie_title,
            format_keywords,
            rating,
            detail_url_path,
            availability_status,
            availability_count,
            is_3d,
            is_70mm,
            is_laser,
            has_subtitles
        FROM listings
        WHERE showing_date >= date('now')
        ORDER BY showing_date, showing_time
    `

    rows, err := db.Query(query)
    if err != nil {
        return nil, err
    }
    defer rows.Close()

    var showings []models.Showing
    for rows.Next() {
        var s models.Showing
        err := rows.Scan(
            &s.ShowingDate,
            &s.ShowingTime,
            &s.ShowingDateTimeUTC,
            &s.MovieTitle,
            &s.FormatKeywords,
            &s.Rating,
            &s.DetailURLPath,
            &s.AvailabilityStatus,
            &s.AvailabilityCount,
            &s.Is3D,
            &s.Is70mm,
            &s.IsLaser,
            &s.HasSubtitles,
        )
        if err != nil {
            return nil, err
        }
        showings = append(showings, s)
    }

    return showings, rows.Err()
}

func GetRecentChanges(db *sql.DB, hours int) ([]models.Showing, error) {
    query := `
        SELECT
            showing_date,
            showing_time,
            showing_datetime_utc,
            movie_title,
            format_keywords,
            rating,
            detail_url_path,
            availability_status,
            availability_count,
            is_3d,
            is_70mm,
            is_laser,
            has_subtitles,
            scraped_at
        FROM listings
        WHERE scraped_at >= datetime('now', '-' || ? || ' hours')
        ORDER BY scraped_at DESC
    `

    rows, err := db.Query(query, hours)
    if err != nil {
        return nil, err
    }
    defer rows.Close()

    var showings []models.Showing
    for rows.Next() {
        var s models.Showing
        err := rows.Scan(
            &s.ShowingDate,
            &s.ShowingTime,
            &s.ShowingDateTimeUTC,
            &s.MovieTitle,
            &s.FormatKeywords,
            &s.Rating,
            &s.DetailURLPath,
            &s.AvailabilityStatus,
            &s.AvailabilityCount,
            &s.Is3D,
            &s.Is70mm,
            &s.IsLaser,
            &s.HasSubtitles,
            &s.ScrapedAt,
        )
        if err != nil {
            return nil, err
        }
        showings = append(showings, s)
    }

    return showings, rows.Err()
}

func GetHealthInfo(db *sql.DB) (models.HealthInfo, error) {
    var info models.HealthInfo

    // Get listing count
    err := db.QueryRow("SELECT COUNT(*) FROM listings WHERE showing_date >= date('now')").Scan(&info.ListingsCount)
    if err != nil {
        return info, err
    }

    // Get date range
    query := `
        SELECT
            MIN(showing_date),
            MAX(showing_date)
        FROM listings
        WHERE showing_date >= date('now')
    `
    err = db.QueryRow(query).Scan(&info.OldestListing, &info.NewestListing)
    if err != nil && err != sql.ErrNoRows {
        return info, err
    }

    // Get last scrape info
    query = `
        SELECT
            MAX(last_scraped),
            status
        FROM scrape_schedule
        WHERE last_scraped IS NOT NULL
        ORDER BY last_scraped DESC
        LIMIT 1
    `
    var lastScrape sql.NullString
    var status sql.NullString
    err = db.QueryRow(query).Scan(&lastScrape, &status)
    if err != nil && err != sql.ErrNoRows {
        return info, err
    }

    if lastScrape.Valid {
        info.LastScrape = lastScrape.String
    }
    if status.Valid {
        info.LastScrapeStatus = status.String
    }

    // Determine overall status
    if info.ListingsCount == 0 {
        info.Status = "unhealthy"
    } else if info.LastScrapeStatus == "error" {
        info.Status = "degraded"
    } else {
        info.Status = "healthy"
    }

    return info, nil
}
```

---

### 4. Data Models

```go
// models/models.go
package models

type Showing struct {
    ShowingDate         string
    ShowingTime         string
    ShowingDateTimeUTC  string
    MovieTitle          string
    FormatKeywords      string
    Rating              string
    DetailURLPath       string
    AvailabilityStatus  string
    AvailabilityCount   int
    Is3D                bool
    Is70mm              bool
    IsLaser             bool
    HasSubtitles        bool
    ScrapedAt           string
}

// DetailURL returns full BFI detail page URL
func (s *Showing) DetailURL() string {
    return "https://whatson.bfi.org.uk/imax/Online/" + s.DetailURLPath
}

// FormatDisplay returns human-readable format string
func (s *Showing) FormatDisplay() string {
    var formats []string
    if s.Is70mm {
        formats = append(formats, "70mm")
    }
    if s.Is3D {
        formats = append(formats, "3D")
    }
    if s.IsLaser {
        formats = append(formats, "IMAX with Laser")
    }
    if s.HasSubtitles {
        formats = append(formats, "Subtitles")
    }

    if len(formats) == 0 {
        return "IMAX"
    }
    return strings.Join(formats, ", ")
}

// AvailabilityDisplay returns human-readable availability
func (s *Showing) AvailabilityDisplay() string {
    switch s.AvailabilityStatus {
    case "G":
        return "Good"
    case "L":
        return "Limited"
    case "S":
        return "Sold Out"
    default:
        return "Unknown"
    }
}

type HealthInfo struct {
    Status           string `json:"status"`
    LastScrape       string `json:"last_scrape"`
    LastScrapeStatus string `json:"last_scrape_status"`
    ListingsCount    int    `json:"listings_count"`
    OldestListing    string `json:"oldest_listing"`
    NewestListing    string `json:"newest_listing"`
}
```

---

### 5. HTTP Handlers

```go
// handlers/listings.go
package handlers

import (
    "database/sql"
    "html/template"
    "log"
    "net/http"

    "webserver/db"
)

func ListingsHandler(database *sql.DB) http.HandlerFunc {
    // Parse templates once at startup
    tmpl := template.Must(template.ParseFiles(
        "templates/base.html",
        "templates/listings.html",
    ))

    return func(w http.ResponseWriter, r *http.Request) {
        // Only accept GET
        if r.Method != http.MethodGet {
            http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
            return
        }

        // Get showings from database
        showings, err := db.GetUpcomingShowings(database)
        if err != nil {
            log.Printf("Error fetching showings: %v", err)
            http.Error(w, "Internal server error", http.StatusInternalServerError)
            return
        }

        // Group showings by date for display
        grouped := groupByDate(showings)

        // Render template
        data := struct {
            Title    string
            Showings map[string][]models.Showing
        }{
            Title:    "BFI IMAX Listings",
            Showings: grouped,
        }

        if err := tmpl.Execute(w, data); err != nil {
            log.Printf("Error rendering template: %v", err)
            http.Error(w, "Internal server error", http.StatusInternalServerError)
        }
    }
}

func groupByDate(showings []models.Showing) map[string][]models.Showing {
    grouped := make(map[string][]models.Showing)
    for _, showing := range showings {
        grouped[showing.ShowingDate] = append(grouped[showing.ShowingDate], showing)
    }
    return grouped
}
```

```go
// handlers/rss.go
package handlers

import (
    "database/sql"
    "encoding/xml"
    "log"
    "net/http"
    "time"

    "webserver/config"
    "webserver/db"
)

type RSS struct {
    XMLName xml.Name `xml:"rss"`
    Version string   `xml:"version,attr"`
    Channel Channel  `xml:"channel"`
}

type Channel struct {
    Title       string `xml:"title"`
    Link        string `xml:"link"`
    Description string `xml:"description"`
    Items       []Item `xml:"item"`
}

type Item struct {
    Title       string `xml:"title"`
    Link        string `xml:"link"`
    Description string `xml:"description"`
    PubDate     string `xml:"pubDate"`
    GUID        string `xml:"guid"`
}

func CurrentRSSHandler(database *sql.DB) http.HandlerFunc {
    cfg := config.Load()

    return func(w http.ResponseWriter, r *http.Request) {
        showings, err := db.GetUpcomingShowings(database)
        if err != nil {
            log.Printf("Error fetching showings for RSS: %v", err)
            http.Error(w, "Internal server error", http.StatusInternalServerError)
            return
        }

        // Build RSS feed
        feed := RSS{
            Version: "2.0",
            Channel: Channel{
                Title:       "BFI IMAX - Current Schedule",
                Link:        cfg.SiteURL,
                Description: "All upcoming BFI IMAX showings",
                Items:       make([]Item, 0, len(showings)),
            },
        }

        for _, s := range showings {
            item := Item{
                Title:       s.MovieTitle + " - " + s.ShowingDate + " " + s.ShowingTime,
                Link:        s.DetailURL(),
                Description: formatShowingDescription(s),
                PubDate:     formatRFC822(s.ShowingDateTimeUTC),
                GUID:        cfg.SiteURL + "/showing/" + s.ShowingDateTimeUTC,
            }
            feed.Channel.Items = append(feed.Channel.Items, item)
        }

        // Render XML
        w.Header().Set("Content-Type", "application/rss+xml; charset=utf-8")
        w.WriteHeader(http.StatusOK)

        enc := xml.NewEncoder(w)
        enc.Indent("", "  ")
        if err := enc.Encode(feed); err != nil {
            log.Printf("Error encoding RSS: %v", err)
        }
    }
}

func DailyRSSHandler(database *sql.DB) http.HandlerFunc {
    cfg := config.Load()

    return func(w http.ResponseWriter, r *http.Request) {
        // Get showings added/changed in last 24 hours
        showings, err := db.GetRecentChanges(database, 24)
        if err != nil {
            log.Printf("Error fetching recent changes for RSS: %v", err)
            http.Error(w, "Internal server error", http.StatusInternalServerError)
            return
        }

        feed := RSS{
            Version: "2.0",
            Channel: Channel{
                Title:       "BFI IMAX - Daily Changes",
                Link:        cfg.SiteURL,
                Description: "New and changed BFI IMAX showings in last 24 hours",
                Items:       make([]Item, 0, len(showings)),
            },
        }

        for _, s := range showings {
            item := Item{
                Title:       s.MovieTitle + " - " + s.ShowingDate + " " + s.ShowingTime,
                Link:        s.DetailURL(),
                Description: formatShowingDescription(s),
                PubDate:     formatRFC822(s.ScrapedAt),
                GUID:        cfg.SiteURL + "/change/" + s.ScrapedAt + "/" + s.ShowingDateTimeUTC,
            }
            feed.Channel.Items = append(feed.Channel.Items, item)
        }

        w.Header().Set("Content-Type", "application/rss+xml; charset=utf-8")
        w.WriteHeader(http.StatusOK)

        enc := xml.NewEncoder(w)
        enc.Indent("", "  ")
        if err := enc.Encode(feed); err != nil {
            log.Printf("Error encoding RSS: %v", err)
        }
    }
}

func formatShowingDescription(s models.Showing) string {
    return fmt.Sprintf("%s at %s<br>Format: %s<br>Rating: %s<br>Availability: %s",
        s.MovieTitle,
        s.ShowingTime,
        s.FormatDisplay(),
        s.Rating,
        s.AvailabilityDisplay(),
    )
}

func formatRFC822(isoTime string) string {
    t, err := time.Parse(time.RFC3339, isoTime)
    if err != nil {
        return time.Now().Format(time.RFC822)
    }
    return t.Format(time.RFC822)
}
```

```go
// handlers/health.go
package handlers

import (
    "database/sql"
    "encoding/json"
    "log"
    "net/http"

    "webserver/db"
)

func HealthHandler(database *sql.DB) http.HandlerFunc {
    return func(w http.ResponseWriter, r *http.Request) {
        info, err := db.GetHealthInfo(database)
        if err != nil {
            log.Printf("Error getting health info: %v", err)
            w.WriteHeader(http.StatusInternalServerError)
            json.NewEncoder(w).Encode(map[string]string{
                "status": "error",
                "error":  err.Error(),
            })
            return
        }

        // Set status code based on health
        switch info.Status {
        case "healthy":
            w.WriteHeader(http.StatusOK)
        case "degraded":
            w.WriteHeader(http.StatusOK)  // 200 but with degraded status
        case "unhealthy":
            w.WriteHeader(http.StatusServiceUnavailable)
        }

        w.Header().Set("Content-Type", "application/json")
        json.NewEncoder(w).Encode(info)
    }
}
```

```go
// handlers/static.go
package handlers

import (
    "net/http"
)

func RobotsHandler(w http.ResponseWriter, r *http.Request) {
    // Restrictive robots.txt
    robots := `User-agent: *
Disallow: /

# BFI IMAX listings - low frequency, don't crawl
# If you want the data, contact us for API access
`
    w.Header().Set("Content-Type", "text/plain")
    w.Write([]byte(robots))
}
```

---

### 6. HTML Templates

```html
<!-- templates/base.html -->
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{.Title}}</title>
    <link rel="stylesheet" href="/static/css/style.css">
    <link rel="alternate" type="application/rss+xml" title="Current Schedule" href="/rss/current">
    <link rel="alternate" type="application/rss+xml" title="Daily Changes" href="/rss/daily">
</head>
<body>
    <header>
        <h1>BFI IMAX Listings</h1>
        <nav>
            <a href="/">Home</a>
            <a href="/rss/current">RSS (Current)</a>
            <a href="/rss/daily">RSS (Changes)</a>
        </nav>
    </header>
    <main>
        {{template "content" .}}
    </main>
    <footer>
        <p>Data scraped from <a href="https://whatson.bfi.org.uk/imax/">BFI IMAX</a></p>
        <p>Updated daily at 02:00 UTC</p>
    </footer>
</body>
</html>
```

```html
<!-- templates/listings.html -->
{{define "content"}}
<div class="listings">
    {{if .Showings}}
        {{range $date, $showings := .Showings}}
        <section class="date-section">
            <h2>{{$date}}</h2>
            <table>
                <thead>
                    <tr>
                        <th>Time</th>
                        <th>Film</th>
                        <th>Format</th>
                        <th>Rating</th>
                        <th>Availability</th>
                        <th>Link</th>
                    </tr>
                </thead>
                <tbody>
                    {{range $showings}}
                    <tr class="showing-row">
                        <td class="time">{{.ShowingTime}}</td>
                        <td class="title">{{.MovieTitle}}</td>
                        <td class="format">{{.FormatDisplay}}</td>
                        <td class="rating">{{.Rating}}</td>
                        <td class="availability {{.AvailabilityStatus}}">
                            {{.AvailabilityDisplay}}
                            {{if .AvailabilityCount}}
                                ({{.AvailabilityCount}} seats)
                            {{end}}
                        </td>
                        <td class="link">
                            <a href="{{.DetailURL}}" target="_blank">Details</a>
                        </td>
                    </tr>
                    {{end}}
                </tbody>
            </table>
        </section>
        {{end}}
    {{else}}
        <p class="no-listings">No upcoming showings found.</p>
    {{end}}
</div>
{{end}}
```

---

### 7. CSS Styling

```css
/* static/css/style.css */
:root {
    --primary-color: #1a1a1a;
    --secondary-color: #e50914;
    --background: #ffffff;
    --text: #1a1a1a;
    --border: #dddddd;
    --good: #28a745;
    --limited: #ffc107;
    --sold-out: #dc3545;
}

* {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}

body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    line-height: 1.6;
    color: var(--text);
    background: var(--background);
    max-width: 1200px;
    margin: 0 auto;
    padding: 1rem;
}

header {
    border-bottom: 2px solid var(--secondary-color);
    padding-bottom: 1rem;
    margin-bottom: 2rem;
}

header h1 {
    color: var(--primary-color);
    margin-bottom: 0.5rem;
}

nav {
    display: flex;
    gap: 1rem;
}

nav a {
    color: var(--primary-color);
    text-decoration: none;
    padding: 0.25rem 0.5rem;
    border-radius: 4px;
}

nav a:hover {
    background: var(--border);
}

.date-section {
    margin-bottom: 2rem;
}

.date-section h2 {
    color: var(--primary-color);
    border-bottom: 1px solid var(--border);
    padding-bottom: 0.5rem;
    margin-bottom: 1rem;
}

table {
    width: 100%;
    border-collapse: collapse;
    margin-bottom: 2rem;
}

th, td {
    padding: 0.75rem;
    text-align: left;
    border-bottom: 1px solid var(--border);
}

th {
    background: var(--primary-color);
    color: white;
    font-weight: 600;
}

tr:hover {
    background: #f8f9fa;
}

.time {
    font-weight: 600;
    white-space: nowrap;
}

.title {
    font-weight: 500;
}

.format {
    font-size: 0.9rem;
    color: #666;
}

.availability.G {
    color: var(--good);
    font-weight: 600;
}

.availability.L {
    color: var(--limited);
    font-weight: 600;
}

.availability.S {
    color: var(--sold-out);
    font-weight: 600;
}

.link a {
    color: var(--secondary-color);
    text-decoration: none;
}

.link a:hover {
    text-decoration: underline;
}

.no-listings {
    text-align: center;
    padding: 3rem;
    color: #666;
    font-size: 1.1rem;
}

footer {
    border-top: 1px solid var(--border);
    padding-top: 1rem;
    margin-top: 3rem;
    text-align: center;
    color: #666;
    font-size: 0.9rem;
}

footer a {
    color: var(--secondary-color);
}

/* Mobile responsive */
@media (max-width: 768px) {
    body {
        padding: 0.5rem;
    }

    table {
        font-size: 0.9rem;
    }

    th, td {
        padding: 0.5rem 0.25rem;
    }

    /* Stack table on mobile */
    table, thead, tbody, th, td, tr {
        display: block;
    }

    thead tr {
        position: absolute;
        top: -9999px;
        left: -9999px;
    }

    tr {
        border: 1px solid var(--border);
        margin-bottom: 1rem;
    }

    td {
        border: none;
        position: relative;
        padding-left: 50%;
    }

    td:before {
        position: absolute;
        left: 0.5rem;
        width: 45%;
        padding-right: 0.5rem;
        white-space: nowrap;
        font-weight: 600;
        content: attr(data-label);
    }
}
```

---

### 8. Build & Deployment

```dockerfile
# Dockerfile
FROM golang:1.21 AS builder

WORKDIR /app

# Copy Go modules
COPY go.mod go.sum ./
RUN go mod download

# Copy source
COPY . .

# Build binary
RUN CGO_ENABLED=1 GOOS=linux go build -o webserver .

# Runtime image
FROM debian:bookworm-slim

# Install SQLite
RUN apt-get update && apt-get install -y \
    sqlite3 \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy binary and assets
COPY --from=builder /app/webserver .
COPY templates ./templates
COPY static ./static

# Expose port
EXPOSE 8080

# Run server
CMD ["./webserver"]
```

```makefile
# Makefile
.PHONY: build run test clean

build:
	go build -o webserver .

run:
	go run .

test:
	go test ./...

clean:
	rm -f webserver

docker-build:
	docker build -t listing-webserver .

docker-run:
	docker run -p 8080:8080 \
		-v $(PWD)/data:/data \
		-e DB_PATH=/data/listing.db \
		listing-webserver
```

---

### 9. Testing

```go
// handlers/listings_test.go
package handlers

import (
    "database/sql"
    "net/http"
    "net/http/httptest"
    "testing"

    _ "github.com/mattn/go-sqlite3"
)

func setupTestDB(t *testing.T) *sql.DB {
    db, err := sql.Open("sqlite3", ":memory:")
    if err != nil {
        t.Fatal(err)
    }

    // Create schema
    schema := `
    CREATE TABLE listings (
        showing_date DATE,
        showing_time TIME,
        showing_datetime_utc TEXT,
        movie_title TEXT,
        format_keywords TEXT,
        rating TEXT,
        detail_url_path TEXT,
        availability_status TEXT,
        availability_count INTEGER,
        is_3d BOOLEAN,
        is_70mm BOOLEAN,
        is_laser BOOLEAN,
        has_subtitles BOOLEAN
    );
    `
    if _, err := db.Exec(schema); err != nil {
        t.Fatal(err)
    }

    // Insert test data
    insert := `
    INSERT INTO listings VALUES
        ('2025-10-26', '10:45', '2025-10-26T09:45:00+00:00', 'Test Film', 'IMAX with Laser', '15', 'test.asp', 'G', 100, 0, 0, 1, 0)
    `
    if _, err := db.Exec(insert); err != nil {
        t.Fatal(err)
    }

    return db
}

func TestListingsHandler(t *testing.T) {
    db := setupTestDB(t)
    defer db.Close()

    handler := ListingsHandler(db)

    req := httptest.NewRequest("GET", "/", nil)
    rec := httptest.NewRecorder()

    handler.ServeHTTP(rec, req)

    if rec.Code != http.StatusOK {
        t.Errorf("Expected status 200, got %d", rec.Code)
    }

    body := rec.Body.String()
    if !strings.Contains(body, "Test Film") {
        t.Error("Expected response to contain 'Test Film'")
    }
}

func TestHealthHandler(t *testing.T) {
    db := setupTestDB(t)
    defer db.Close()

    handler := HealthHandler(db)

    req := httptest.NewRequest("GET", "/health", nil)
    rec := httptest.NewRecorder()

    handler.ServeHTTP(rec, req)

    if rec.Code != http.StatusOK {
        t.Errorf("Expected status 200, got %d", rec.Code)
    }

    var health models.HealthInfo
    if err := json.NewDecoder(rec.Body).Decode(&health); err != nil {
        t.Fatalf("Failed to decode JSON: %v", err)
    }

    if health.Status != "healthy" {
        t.Errorf("Expected status 'healthy', got '%s'", health.Status)
    }

    if health.ListingsCount != 1 {
        t.Errorf("Expected 1 listing, got %d", health.ListingsCount)
    }
}
```

---

### 10. Monitoring & Metrics

```go
// Future enhancement: Prometheus metrics
package metrics

import (
    "github.com/prometheus/client_golang/prometheus"
    "github.com/prometheus/client_golang/prometheus/promauto"
)

var (
    httpRequestsTotal = promauto.NewCounterVec(
        prometheus.CounterOpts{
            Name: "http_requests_total",
            Help: "Total HTTP requests",
        },
        []string{"path", "method", "status"},
    )

    httpRequestDuration = promauto.NewHistogramVec(
        prometheus.HistogramOpts{
            Name:    "http_request_duration_seconds",
            Help:    "HTTP request duration",
            Buckets: prometheus.DefBuckets,
        },
        []string{"path", "method"},
    )

    dbQueryDuration = promauto.NewHistogramVec(
        prometheus.HistogramOpts{
            Name:    "db_query_duration_seconds",
            Help:    "Database query duration",
            Buckets: prometheus.DefBuckets,
        },
        []string{"query"},
    )
)
```

---

## Success Criteria

Web server is successful if:

- [ ] Serves HTML page with all upcoming showings
- [ ] RSS feeds work (/rss/current, /rss/daily)
- [ ] Health endpoint returns accurate status
- [ ] Page loads in <500ms for typical dataset
- [ ] Mobile-responsive design
- [ ] Graceful shutdown on SIGTERM
- [ ] Handles database connection errors gracefully
- [ ] Logs all requests
- [ ] robots.txt is restrictive
- [ ] Works on Raspberry Pi (ARM architecture)

---

## Next Steps

1. [ ] **Review**: Simon reviews design
2. [ ] **Implement**: Core server and handlers
3. [ ] **Implement**: Database queries
4. [ ] **Implement**: HTML templates
5. [ ] **Test**: Unit tests for handlers
6. [ ] **Test**: Integration with Python scraper
7. [ ] **Test**: Load testing
8. [ ] **Document**: Update decision.md

---

## Related Documents

- [Decision](../decision.md) - Phase 1/2/3 evolution plan
- [SQLite Schema](./sqlite-schema-design.md) - Database structure
- [Daily Maintenance](./daily-maintenance-workflow.md) - Integration with scraper
- [Outcomes](../outcomes.md) - Outcome 4: Web Presentation requirements
