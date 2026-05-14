package main

import (
	"database/sql"
	"fmt"
	"html/template"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"time"

	_ "github.com/mattn/go-sqlite3"
)

const Version = "1.0.0"

var (
	db        *sql.DB
	templates *template.Template
)

func main() {
	log.SetFlags(log.LstdFlags | log.Lshortfile)
	log.Println("Starting Strategy Tracker...")

	// Initialize database
	var err error
	dbPath := os.Getenv("DB_PATH")
	if dbPath == "" {
		dbPath = "data/strategies.db"
	}

	log.Printf("Opening database at: %s", dbPath)
	// Use WAL mode for better concurrency with Litestream
	db, err = sql.Open("sqlite3", dbPath+"?_journal_mode=WAL&_busy_timeout=5000")
	if err != nil {
		log.Fatal("Failed to open database:", err)
	}
	defer db.Close()

	// Test database connection
	if err = db.Ping(); err != nil {
		log.Fatal("Failed to ping database:", err)
	}
	log.Println("✅ Database connected successfully")

	// Load templates with custom functions
	funcMap := template.FuncMap{
		"mul":     func(a, b float64) float64 { return a * b },
		"add":     func(a, b int) int { return a + b },
		"sub":     func(a, b float64) float64 { return a - b },
		"div":     func(a, b float64) float64 { return a / b },
		"divf":    func(a, b float64) float64 { return a / b },
		"float64": func(a int) float64 { return float64(a) },
		"formatDate": func(dateStr string) string {
			// Remove time portion from ISO datetime string
			if len(dateStr) >= 10 {
				return dateStr[:10]
			}
			return dateStr
		},
		"formatDateLong": func(dateStr string) string {
			// Parse YYYY-MM-DD or YYYY-MM-DDTHH:MM:SSZ and return "January 2, 2006"
			s := dateStr
			if len(s) > 10 {
				s = s[:10]
			}
			t, err := time.Parse("2006-01-02", s)
			if err != nil {
				return dateStr
			}
			// Format: "May 8, 2026" (no leading zero on day)
			return t.Format("January 2, 2006")
		},
		"formatMonthYear": func(dateStr string) string {
			// Parse ISO datetime string and format as "Jan, 2024"
			t, err := time.Parse("2006-01-02T15:04:05Z", dateStr)
			if err != nil {
				// Try without time portion
				t, err = time.Parse("2006-01-02", dateStr)
				if err != nil {
					return dateStr // Return original if parsing fails
				}
			}
			return t.Format("Jan, 2006")
		},
	}

	templatesPath := filepath.Join("templates", "*.html")
	log.Printf("Loading templates from: %s", templatesPath)
	templates = template.Must(template.New("").Funcs(funcMap).ParseGlob(templatesPath))
	log.Printf("✅ Loaded %d templates", len(templates.Templates()))

	// Set up routes
	log.Println("Setting up routes...")
	http.HandleFunc("/", homeHandler)
	http.HandleFunc("/gtaa6", gtaa6Handler)
	http.HandleFunc("/gtaa3", gtaa3Handler)
	http.HandleFunc("/dual-momentum", dualMomentumHandler)

	// ETF detail pages
	http.HandleFunc("/etf/", etfHandler)

	// Backtest routes
	http.HandleFunc("/backtests", backtestsIndexHandler)
	http.HandleFunc("/backtests/detail", backtestDetailHandler)

	// Serve static files
	fs := http.FileServer(http.Dir("static"))
	http.Handle("/static/", http.StripPrefix("/static/", fs))

	// Start server
	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}

	addr := fmt.Sprintf(":%s", port)
	log.Printf("✅ Server starting on http://localhost%s", addr)
	log.Println("Press Ctrl+C to stop")
	log.Fatal(http.ListenAndServe(addr, nil))
}

// Data structures
type Strategy struct {
	Name          string
	SignalDate    string
	Holdings      []Holding
	TotalCash     float64
	NumPositions  int
	LastUpdated   string
}

type Holding struct {
	Symbol        string
	Name          string
	Allocation    float64
	Price         float64
	MA200         float64
	AboveMA       bool
	MomentumScore float64
	Reason        string
	IsCash        bool
}

type AssetData struct {
	Symbol      string
	Description string
	URL         string
	Price       float64
	MA200       float64
	MA215       float64
	AboveMA     bool
	ROC1M       float64
	ROC3M       float64
	ROC6M       float64
	ROC12M      float64
	AvgROC      float64
	Rank        int
	IsSelected6 bool
	IsSelected3 bool
}

// Asset descriptions
var assetDescriptions = map[string]string{
	"SPMO": "US Large Cap Momen.",
	"MTUM": "US Momentum Factor",
	"VBK":  "US Small Cap Growth",
	"VBR":  "US Small Cap Value",
	"VTV":  "US Large Cap Value",
	"VEA":  "Developed Markets",
	"VWO":  "Emerging Markets",
	"VNQ":  "US Real Estate",
	"QQQM": "US Tech (Nasdaq)",
	"QQQ":  "US Tech (Nasdaq)",
	"GSG":  "Commodities",
	"IAU":  "Gold",
	"VCIT": "Corporate Bonds (Int)",
	"VGIT": "Gov Bonds (Int)",
	"VGLT": "Gov Bonds (Long)",
	"IGOV": "Intl Gov Bonds",
	"VOO":  "US Total Market",
	"VEU":  "International Equity",
	"BIL":  "Short-Term T-Bills (Cash)",
}

// Asset URLs - links to fund provider pages
var assetURLs = map[string]string{
	"SPMO": "https://www.invesco.com/us/financial-products/etfs/product-detail?productId=SPMO",
	"MTUM": "https://www.ishares.com/us/products/251614/ishares-msci-usa-momentum-factor-etf",
	"VBK":  "https://investor.vanguard.com/investment-products/etfs/profile/vbk",
	"VBR":  "https://investor.vanguard.com/investment-products/etfs/profile/vbr",
	"VTV":  "https://investor.vanguard.com/investment-products/etfs/profile/vtv",
	"VEA":  "https://investor.vanguard.com/investment-products/etfs/profile/vea",
	"VWO":  "https://investor.vanguard.com/investment-products/etfs/profile/vwo",
	"VNQ":  "https://investor.vanguard.com/investment-products/etfs/profile/vnq",
	"QQQM": "https://www.invesco.com/us/financial-products/etfs/product-detail?productId=QQQM",
	"QQQ":  "https://www.invesco.com/us/financial-products/etfs/product-detail?productId=QQQ",
	"GSG":  "https://www.ishares.com/us/products/239757/ishares-sp-gsci-commodityindexed-trust-fund",
	"IAU":  "https://www.ishares.com/us/products/239561/ishares-gold-trust-fund",
	"VCIT": "https://investor.vanguard.com/investment-products/etfs/profile/vcit",
	"VGIT": "https://investor.vanguard.com/investment-products/etfs/profile/vgit",
	"VGLT": "https://investor.vanguard.com/investment-products/etfs/profile/vglt",
	"IGOV": "https://www.ishares.com/us/products/239830/ishares-international-treasury-bond-etf",
	"VOO":  "https://investor.vanguard.com/investment-products/etfs/profile/voo",
	"VEU":  "https://investor.vanguard.com/investment-products/etfs/profile/veu",
	"BIL":  "https://www.ssga.com/us/en/individual/etfs/funds/spdr-bloomberg-1-3-month-t-bill-etf-bil",
}

// Asset expense ratios
var assetExpenseRatios = map[string]string{
	"SPMO": "0.13%",
	"MTUM": "0.15%",
	"VBK":  "0.07%",
	"VBR":  "0.07%",
	"VTV":  "0.04%",
	"VEA":  "0.05%",
	"VWO":  "0.08%",
	"VNQ":  "0.13%",
	"QQQM": "0.15%",
	"QQQ":  "0.20%",
	"GSG":  "0.75%",
	"IAU":  "0.25%",
	"VCIT": "0.04%",
	"VGIT": "0.04%",
	"VGLT": "0.04%",
	"IGOV": "0.35%",
	"BIL":  "0.14%",
	"VOO":  "0.03%",
	"VEU":  "0.07%",
}

type DualMomentumData struct {
	USSymbol     string
	USURL        string
	USPrice      float64
	USROC12M     float64
	IntlSymbol   string
	IntlURL      string
	IntlPrice    float64
	IntlROC12M   float64
	CashSymbol   string
	CashURL      string
	CashPrice    float64
	CashYield    float64
	Selected     string
	SignalDate   string
}

type HomePage struct {
	GTAAAssets   []AssetData
	DualMomentum DualMomentumData
	SignalDate   string
	Version      string
}

type ETFPriceRow struct {
	Date  string
	Price float64
}

type ETFPage struct {
	Symbol       string
	Description  string
	ExternalURL  string
	ExpenseRatio string
	CurrentPrice float64
	MA200        float64
	MA215        float64
	AboveMA200   bool
	AboveMA215   bool
	Prices       []ETFPriceRow
	Version      string
}

// Handlers
func homeHandler(w http.ResponseWriter, r *http.Request) {
	log.Printf("Request: %s %s from %s", r.Method, r.URL.Path, r.RemoteAddr)

	// Get all GTAA assets with indicators
	gtaaAssets, signalDate, err := getGTAAAssets()
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		log.Printf("Error loading GTAA assets: %v", err)
		return
	}
	log.Printf("Loaded %d GTAA assets for signal date %s", len(gtaaAssets), signalDate)

	// Get dual momentum data
	dualMomentum, err := getDualMomentumData()
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		log.Printf("Error loading dual momentum: %v", err)
		return
	}
	log.Printf("Loaded dual momentum data: %s selected", dualMomentum.Selected)

	data := HomePage{
		GTAAAssets:   gtaaAssets,
		DualMomentum: dualMomentum,
		SignalDate:   signalDate,
		Version:      Version,
	}

	log.Printf("Executing template with %d assets", len(data.GTAAAssets))
	if err := templates.ExecuteTemplate(w, "home.html", data); err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		log.Printf("Template error: %v", err)
		return
	}
	log.Printf("Template executed successfully")
}

func gtaa6Handler(w http.ResponseWriter, r *http.Request) {
	strat, err := getLatestStrategy("gtaa6")
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	// Get v2 backtests with full analysis (drawdowns & rolling returns)
	backtests, err := getBacktestsWithAnalysis("gtaa6", "v2_")
	if err != nil {
		log.Printf("Error loading backtests: %v", err)
		// Continue without backtests rather than failing
	}

	data := struct {
		Strategy
		Backtests []BacktestWithAnalysis
		Version   string
	}{
		Strategy:  strat,
		Backtests: backtests,
		Version:   Version,
	}

	if err := templates.ExecuteTemplate(w, "gtaa6.html", data); err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		log.Printf("Template error: %v", err)
	}
}

func gtaa3Handler(w http.ResponseWriter, r *http.Request) {
	strat, err := getLatestStrategy("gtaa3")
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	// Get backtests for this strategy
	backtests, err := getBacktestsForStrategy("gtaa3")
	if err != nil {
		log.Printf("Error loading backtests: %v", err)
		// Continue without backtests rather than failing
	}

	data := struct {
		Strategy
		Backtests []BacktestSummary
		Version   string
	}{
		Strategy:  strat,
		Backtests: backtests,
		Version:   Version,
	}

	if err := templates.ExecuteTemplate(w, "gtaa3.html", data); err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		log.Printf("Template error: %v", err)
	}
}

func dualMomentumHandler(w http.ResponseWriter, r *http.Request) {
	strat, err := getLatestStrategy("dual_momentum")
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	// Get v2 backtests with full analysis (drawdowns & rolling returns)
	backtests, err := getBacktestsWithAnalysis("dual_momentum", "v2_")
	if err != nil {
		log.Printf("Error loading backtests: %v", err)
		// Continue without backtests rather than failing
	}

	data := struct {
		Strategy
		Backtests []BacktestWithAnalysis
		Version   string
	}{
		Strategy:  strat,
		Backtests: backtests,
		Version:   Version,
	}

	if err := templates.ExecuteTemplate(w, "dual_momentum.html", data); err != nil{
		http.Error(w, err.Error(), http.StatusInternalServerError)
		log.Printf("Template error: %v", err)
	}
}

func etfHandler(w http.ResponseWriter, r *http.Request) {
	symbol := strings.ToUpper(strings.TrimSpace(strings.TrimPrefix(r.URL.Path, "/etf/")))
	if symbol == "" {
		http.NotFound(w, r)
		return
	}

	var tickerID int
	if err := db.QueryRow("SELECT id FROM tickers WHERE symbol = ?", symbol).Scan(&tickerID); err != nil {
		http.NotFound(w, r)
		return
	}

	var currentPrice, ma200, ma215 float64
	db.QueryRow(`
		SELECT p.adj_close, COALESCE(i.ma_200, 0), COALESCE(i.ma_215, 0)
		FROM prices p
		LEFT JOIN indicators i ON p.ticker_id = i.ticker_id AND p.date = i.date
		WHERE p.ticker_id = ?
		ORDER BY p.date DESC
		LIMIT 1
	`, tickerID).Scan(&currentPrice, &ma200, &ma215)

	rows, err := db.Query(`
		SELECT date, adj_close FROM prices
		WHERE ticker_id = ?
		ORDER BY date DESC
		LIMIT 250
	`, tickerID)
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}
	defer rows.Close()

	var prices []ETFPriceRow
	for rows.Next() {
		var row ETFPriceRow
		if err := rows.Scan(&row.Date, &row.Price); err != nil {
			continue
		}
		prices = append(prices, row)
	}

	description := assetDescriptions[symbol]
	if description == "" {
		description = symbol
	}
	expenseRatio := assetExpenseRatios[symbol]
	if expenseRatio == "" {
		expenseRatio = "N/A"
	}
	externalURL := assetURLs[symbol]
	if externalURL == "" {
		externalURL = "https://finance.yahoo.com/quote/" + symbol
	}

	page := ETFPage{
		Symbol:       symbol,
		Description:  description,
		ExternalURL:  externalURL,
		ExpenseRatio: expenseRatio,
		CurrentPrice: currentPrice,
		MA200:        ma200,
		MA215:        ma215,
		AboveMA200:   ma200 > 0 && currentPrice > ma200,
		AboveMA215:   ma215 > 0 && currentPrice > ma215,
		Prices:       prices,
		Version:      Version,
	}

	if err := templates.ExecuteTemplate(w, "etf.html", page); err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		log.Printf("Template error: %v", err)
	}
}

// Database queries
func getGTAAAssets() ([]AssetData, string, error) {
	var assets []AssetData

	// Get latest signal date
	var signalDate string
	err := db.QueryRow(`
		SELECT signal_date FROM strategy_signals
		WHERE strategy_name = 'gtaa6'
		ORDER BY signal_date DESC LIMIT 1
	`).Scan(&signalDate)
	if err != nil {
		return nil, "", fmt.Errorf("no signals found: %w", err)
	}

	// Get all GTAA universe tickers with their latest data
	query := `
		SELECT
			t.symbol,
			p.adj_close,
			COALESCE(i.ma_200, 0) as ma_200,
			COALESCE(i.ma_215, 0) as ma_215,
			COALESCE(i.roc_1m, 0) as roc_1m,
			COALESCE(i.roc_3m, 0) as roc_3m,
			COALESCE(i.roc_6m, 0) as roc_6m,
			COALESCE(i.roc_12m, 0) as roc_12m,
			COALESCE(i.avg_roc, 0) as avg_roc
		FROM strategy_universes su
		JOIN tickers t ON su.ticker_id = t.id
		JOIN (
			SELECT ticker_id, MAX(date) as max_date
			FROM prices
			WHERE date <= ?
			GROUP BY ticker_id
		) latest ON t.id = latest.ticker_id
		JOIN prices p ON t.id = p.ticker_id AND p.date = latest.max_date
		LEFT JOIN indicators i ON t.id = i.ticker_id AND p.date = i.date
		WHERE su.strategy_name = 'gtaa6' AND t.symbol != 'BIL'
		ORDER BY COALESCE(i.avg_roc, 0) DESC
	`

	rows, err := db.Query(query, signalDate)
	if err != nil {
		return nil, "", fmt.Errorf("failed to fetch assets: %w", err)
	}
	defer rows.Close()

	rank := 1
	for rows.Next() {
		var asset AssetData

		err := rows.Scan(&asset.Symbol, &asset.Price, &asset.MA200, &asset.MA215, &asset.ROC1M, &asset.ROC3M, &asset.ROC6M, &asset.ROC12M, &asset.AvgROC)
		if err != nil {
			log.Printf("Error scanning asset %s: %v", asset.Symbol, err)
			continue
		}

		asset.Description = assetDescriptions[asset.Symbol]
		if asset.Description == "" {
			asset.Description = asset.Symbol
		}

		asset.URL = assetURLs[asset.Symbol]
		if asset.URL == "" {
			asset.URL = "https://finance.yahoo.com/quote/" + asset.Symbol
		}

		asset.AboveMA = asset.MA200 > 0 && asset.Price > asset.MA200
		asset.Rank = rank
		asset.IsSelected6 = rank <= 6 && asset.AboveMA
		asset.IsSelected3 = rank <= 3 && asset.AboveMA

		assets = append(assets, asset)
		rank++
	}

	return assets, signalDate, nil
}

func getDualMomentumData() (DualMomentumData, error) {
	var dm DualMomentumData

	// Get latest signal
	var signalID int
	err := db.QueryRow(`
		SELECT id, signal_date FROM strategy_signals
		WHERE strategy_name = 'dual_momentum'
		ORDER BY signal_date DESC LIMIT 1
	`).Scan(&signalID, &dm.SignalDate)
	if err != nil {
		return dm, fmt.Errorf("no dual momentum signals found: %w", err)
	}

	// Get selected holding
	var selectedSymbol string
	err = db.QueryRow(`
		SELECT t.symbol FROM holdings h
		JOIN tickers t ON h.ticker_id = t.id
		WHERE h.signal_id = ?
	`, signalID).Scan(&selectedSymbol)
	if err != nil {
		log.Printf("Warning: Could not get selected holding: %v", err)
	}
	dm.Selected = selectedSymbol

	// Get US data (VOO)
	dm.USSymbol = "VOO"
	dm.USURL = assetURLs["VOO"]
	var usPrice, usROC sql.NullFloat64
	err = db.QueryRow(`
		SELECT p.adj_close, COALESCE(i.roc_12m, 0)
		FROM tickers t
		JOIN prices p ON t.id = p.ticker_id
		LEFT JOIN indicators i ON t.id = i.ticker_id AND p.date = i.date
		WHERE t.symbol = 'VOO'
		AND p.date = (SELECT MAX(date) FROM prices WHERE ticker_id = t.id AND date <= ?)
	`, dm.SignalDate).Scan(&usPrice, &usROC)
	if err != nil {
		log.Printf("Warning: Could not get VOO data: %v", err)
	} else {
		dm.USPrice = usPrice.Float64
		dm.USROC12M = usROC.Float64
	}

	// Get International data (VEU)
	dm.IntlSymbol = "VEU"
	dm.IntlURL = assetURLs["VEU"]
	var intlPrice, intlROC sql.NullFloat64
	err = db.QueryRow(`
		SELECT p.adj_close, COALESCE(i.roc_12m, 0)
		FROM tickers t
		JOIN prices p ON t.id = p.ticker_id
		LEFT JOIN indicators i ON t.id = i.ticker_id AND p.date = i.date
		WHERE t.symbol = 'VEU'
		AND p.date = (SELECT MAX(date) FROM prices WHERE ticker_id = t.id AND date <= ?)
	`, dm.SignalDate).Scan(&intlPrice, &intlROC)
	if err != nil {
		log.Printf("Warning: Could not get VEU data: %v", err)
	} else {
		dm.IntlPrice = intlPrice.Float64
		dm.IntlROC12M = intlROC.Float64
	}

	// Get Cash data (BIL)
	dm.CashSymbol = "BIL"
	dm.CashURL = assetURLs["BIL"]
	var cashPrice, cashROC sql.NullFloat64
	err = db.QueryRow(`
		SELECT p.adj_close, COALESCE(i.roc_12m, 0)
		FROM tickers t
		JOIN prices p ON t.id = p.ticker_id
		LEFT JOIN indicators i ON t.id = i.ticker_id AND p.date = i.date
		WHERE t.symbol = 'BIL'
		AND p.date = (SELECT MAX(date) FROM prices WHERE ticker_id = t.id AND date <= ?)
	`, dm.SignalDate).Scan(&cashPrice, &cashROC)
	if err != nil {
		log.Printf("Warning: Could not get BIL data: %v", err)
	} else {
		dm.CashPrice = cashPrice.Float64
		dm.CashYield = cashROC.Float64
	}

	log.Printf("Dual Momentum: VOO=$%.2f (ROC: %.2f%%), VEU=$%.2f (ROC: %.2f%%), BIL=$%.2f (12M ROC: %.2f%%), Selected=%s",
		dm.USPrice, dm.USROC12M*100, dm.IntlPrice, dm.IntlROC12M*100, dm.CashPrice, dm.CashYield*100, dm.Selected)

	return dm, nil
}

func getLatestStrategy(strategyName string) (Strategy, error) {
	var strat Strategy

	// Map internal names to display names
	nameMap := map[string]string{
		"gtaa6":          "GTAA AGG 6",
		"gtaa3":          "GTAA AGG 3",
		"dual_momentum":  "Dual Momentum ROC12",
	}
	strat.Name = nameMap[strategyName]

	// Get latest signal
	query := `
		SELECT id, signal_date, created_at
		FROM strategy_signals
		WHERE strategy_name = ?
		ORDER BY signal_date DESC
		LIMIT 1
	`

	var signalID int
	var createdAt string
	err := db.QueryRow(query, strategyName).Scan(&signalID, &strat.SignalDate, &createdAt)
	if err != nil {
		return strat, fmt.Errorf("no signals found for %s: %w", strategyName, err)
	}

	strat.LastUpdated = createdAt

	// Get holdings for this signal
	holdingsQuery := `
		SELECT
			t.symbol,
			t.name,
			h.allocation,
			h.is_cash,
			h.price,
			h.ma_200,
			h.momentum_score,
			h.reason
		FROM holdings h
		JOIN tickers t ON h.ticker_id = t.id
		WHERE h.signal_id = ?
		ORDER BY h.allocation DESC, t.symbol
	`

	rows, err := db.Query(holdingsQuery, signalID)
	if err != nil {
		return strat, fmt.Errorf("failed to fetch holdings: %w", err)
	}
	defer rows.Close()

	strat.Holdings = []Holding{}
	totalCash := 0.0

	for rows.Next() {
		var h Holding
		var name sql.NullString
		var price sql.NullFloat64
		var ma200 sql.NullFloat64
		var momentum sql.NullFloat64
		var reason sql.NullString

		err := rows.Scan(
			&h.Symbol,
			&name,
			&h.Allocation,
			&h.IsCash,
			&price,
			&ma200,
			&momentum,
			&reason,
		)
		if err != nil {
			log.Printf("Error scanning holding: %v", err)
			continue
		}

		h.Name = name.String
		h.Price = price.Float64
		h.MA200 = ma200.Float64
		h.MomentumScore = momentum.Float64
		h.Reason = reason.String

		if h.Price > 0 && h.MA200 > 0 {
			h.AboveMA = h.Price > h.MA200
		}

		if h.IsCash {
			totalCash += h.Allocation
		} else {
			strat.NumPositions++
		}

		strat.Holdings = append(strat.Holdings, h)
	}

	strat.TotalCash = totalCash

	return strat, nil
}

// Backtest data structures
type BacktestConfig struct {
	ID                 int
	StrategyName       string
	Variant            string
	UniverseETFs       string
	StartDate          string
	EndDate            string
	InitialCapital     float64
	RebalanceFrequency string
	TopN               sql.NullInt64
	Description        string
}

type BacktestMetrics struct {
	ConfigID            int
	PeriodStart         string
	PeriodEnd           string
	Years               float64
	PreTaxCAGR          float64
	AfterTaxCAGR        float64
	TaxDrag             float64
	PreTaxFinal         float64
	AfterTaxFinal       float64
	TotalTaxes          float64
	EffectiveTaxRate    float64
	MaxDrawdown         sql.NullFloat64
	MaxDDPeakDate       sql.NullString
	MaxDDTroughDate     sql.NullString
	MaxDDRecoveryDate   sql.NullString
	MaxDDDurationMonths sql.NullInt64
	NumTransactions     sql.NullInt64
}

type MonthlyReturn struct {
	Date              string
	PreTaxValue       float64
	AfterTaxValue     float64
	PreTaxReturn      sql.NullFloat64
	AfterTaxReturn    sql.NullFloat64
	TaxPaidCumulative float64
	CashWeight        float64
	Holdings          sql.NullString
	NumHoldings       sql.NullInt64
}

type AnnualReturn struct {
	Year           int
	PreTaxReturn   float64
	AfterTaxReturn float64
	TaxDrag        float64
	PreTaxEnd      float64
	AfterTaxEnd    float64
}

type Drawdown struct {
	Rank           int
	Drawdown       float64
	PeakDate       string
	TroughDate     string
	RecoveryDate   sql.NullString
	DurationMonths sql.NullInt64
}

type RollingReturn struct {
	PeriodYears    int
	BestCAGR       float64
	BestStartDate  string
	BestEndDate    string
	WorstCAGR      float64
	WorstStartDate string
	WorstEndDate   string
}

type BacktestSummary struct {
	Config  BacktestConfig
	Metrics BacktestMetrics
}

type BacktestWithAnalysis struct {
	Config         BacktestConfig
	Metrics        BacktestMetrics
	Drawdowns      []Drawdown
	RollingReturns []RollingReturn
}

type BacktestDetail struct {
	Config         BacktestConfig
	Metrics        BacktestMetrics
	AnnualReturns  []AnnualReturn
	MonthlyReturns []MonthlyReturn
	Drawdowns      []Drawdown
	RollingReturns []RollingReturn
	Version        string
}

// Database query functions for backtests

func getAllBacktestSummaries() ([]BacktestSummary, error) {
	query := `
		SELECT 
			c.id, c.strategy_name, c.variant, c.universe_etfs, 
			c.start_date, c.end_date, c.initial_capital, c.rebalance_frequency,
			c.top_n, c.description,
			m.period_start, m.period_end, m.years,
			m.pre_tax_cagr, m.after_tax_cagr, m.tax_drag,
			m.pre_tax_final, m.after_tax_final, m.total_taxes,
			m.effective_tax_rate, m.max_drawdown, m.num_transactions
		FROM backtest_configs c
		JOIN backtest_metrics m ON c.id = m.config_id
		ORDER BY m.after_tax_cagr DESC
	`

	rows, err := db.Query(query)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var summaries []BacktestSummary
	for rows.Next() {
		var s BacktestSummary
		err := rows.Scan(
			&s.Config.ID, &s.Config.StrategyName, &s.Config.Variant, &s.Config.UniverseETFs,
			&s.Config.StartDate, &s.Config.EndDate, &s.Config.InitialCapital, &s.Config.RebalanceFrequency,
			&s.Config.TopN, &s.Config.Description,
			&s.Metrics.PeriodStart, &s.Metrics.PeriodEnd, &s.Metrics.Years,
			&s.Metrics.PreTaxCAGR, &s.Metrics.AfterTaxCAGR, &s.Metrics.TaxDrag,
			&s.Metrics.PreTaxFinal, &s.Metrics.AfterTaxFinal, &s.Metrics.TotalTaxes,
			&s.Metrics.EffectiveTaxRate, &s.Metrics.MaxDrawdown, &s.Metrics.NumTransactions,
		)
		if err != nil {
			return nil, err
		}
		summaries = append(summaries, s)
	}

	return summaries, nil
}

func getBacktestsForStrategy(strategyName string) ([]BacktestSummary, error) {
	query := `
		SELECT
			c.id, c.strategy_name, c.variant, c.universe_etfs,
			c.start_date, c.end_date, c.initial_capital, c.rebalance_frequency,
			c.top_n, c.description,
			m.period_start, m.period_end, m.years,
			m.pre_tax_cagr, m.after_tax_cagr, m.tax_drag,
			m.pre_tax_final, m.after_tax_final, m.total_taxes,
			m.effective_tax_rate, m.max_drawdown, m.num_transactions
		FROM backtest_configs c
		JOIN backtest_metrics m ON c.id = m.config_id
		WHERE c.strategy_name = ?
		ORDER BY m.after_tax_cagr DESC
	`

	rows, err := db.Query(query, strategyName)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var summaries []BacktestSummary
	for rows.Next() {
		var s BacktestSummary
		err := rows.Scan(
			&s.Config.ID, &s.Config.StrategyName, &s.Config.Variant, &s.Config.UniverseETFs,
			&s.Config.StartDate, &s.Config.EndDate, &s.Config.InitialCapital, &s.Config.RebalanceFrequency,
			&s.Config.TopN, &s.Config.Description,
			&s.Metrics.PeriodStart, &s.Metrics.PeriodEnd, &s.Metrics.Years,
			&s.Metrics.PreTaxCAGR, &s.Metrics.AfterTaxCAGR, &s.Metrics.TaxDrag,
			&s.Metrics.PreTaxFinal, &s.Metrics.AfterTaxFinal, &s.Metrics.TotalTaxes,
			&s.Metrics.EffectiveTaxRate, &s.Metrics.MaxDrawdown, &s.Metrics.NumTransactions,
		)
		if err != nil {
			return nil, err
		}
		summaries = append(summaries, s)
	}

	return summaries, nil
}

func getBacktestsForStrategyWithFilter(strategyName, variantPrefix string) ([]BacktestSummary, error) {
	query := `
		SELECT
			c.id, c.strategy_name, c.variant, c.universe_etfs,
			c.start_date, c.end_date, c.initial_capital, c.rebalance_frequency,
			c.top_n, c.description,
			m.period_start, m.period_end, m.years,
			m.pre_tax_cagr, m.after_tax_cagr, m.tax_drag,
			m.pre_tax_final, m.after_tax_final, m.total_taxes,
			m.effective_tax_rate, m.max_drawdown, m.num_transactions
		FROM backtest_configs c
		JOIN backtest_metrics m ON c.id = m.config_id
		WHERE c.strategy_name = ? AND c.variant LIKE ?
		ORDER BY m.after_tax_cagr DESC
	`

	rows, err := db.Query(query, strategyName, variantPrefix+"%")
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var summaries []BacktestSummary
	for rows.Next() {
		var s BacktestSummary
		err := rows.Scan(
			&s.Config.ID, &s.Config.StrategyName, &s.Config.Variant, &s.Config.UniverseETFs,
			&s.Config.StartDate, &s.Config.EndDate, &s.Config.InitialCapital, &s.Config.RebalanceFrequency,
			&s.Config.TopN, &s.Config.Description,
			&s.Metrics.PeriodStart, &s.Metrics.PeriodEnd, &s.Metrics.Years,
			&s.Metrics.PreTaxCAGR, &s.Metrics.AfterTaxCAGR, &s.Metrics.TaxDrag,
			&s.Metrics.PreTaxFinal, &s.Metrics.AfterTaxFinal, &s.Metrics.TotalTaxes,
			&s.Metrics.EffectiveTaxRate, &s.Metrics.MaxDrawdown, &s.Metrics.NumTransactions,
		)
		if err != nil {
			return nil, err
		}
		summaries = append(summaries, s)
	}

	return summaries, nil
}

func getBacktestsWithAnalysis(strategyName, variantPrefix string) ([]BacktestWithAnalysis, error) {
	query := `
		SELECT
			c.id, c.strategy_name, c.variant, c.universe_etfs,
			c.start_date, c.end_date, c.initial_capital, c.rebalance_frequency,
			c.top_n, c.description,
			m.period_start, m.period_end, m.years,
			m.pre_tax_cagr, m.after_tax_cagr, m.tax_drag,
			m.pre_tax_final, m.after_tax_final, m.total_taxes,
			m.effective_tax_rate, m.max_drawdown, m.num_transactions
		FROM backtest_configs c
		JOIN backtest_metrics m ON c.id = m.config_id
		WHERE c.strategy_name = ? AND c.variant LIKE ?
		ORDER BY m.after_tax_cagr DESC
	`

	rows, err := db.Query(query, strategyName, variantPrefix+"%")
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var backtests []BacktestWithAnalysis
	for rows.Next() {
		var bt BacktestWithAnalysis
		err := rows.Scan(
			&bt.Config.ID, &bt.Config.StrategyName, &bt.Config.Variant, &bt.Config.UniverseETFs,
			&bt.Config.StartDate, &bt.Config.EndDate, &bt.Config.InitialCapital, &bt.Config.RebalanceFrequency,
			&bt.Config.TopN, &bt.Config.Description,
			&bt.Metrics.PeriodStart, &bt.Metrics.PeriodEnd, &bt.Metrics.Years,
			&bt.Metrics.PreTaxCAGR, &bt.Metrics.AfterTaxCAGR, &bt.Metrics.TaxDrag,
			&bt.Metrics.PreTaxFinal, &bt.Metrics.AfterTaxFinal, &bt.Metrics.TotalTaxes,
			&bt.Metrics.EffectiveTaxRate, &bt.Metrics.MaxDrawdown, &bt.Metrics.NumTransactions,
		)
		if err != nil {
			return nil, err
		}

		// Load drawdowns for this backtest
		drawdownQuery := `
			SELECT rank, drawdown, peak_date, trough_date, recovery_date, duration_months
			FROM backtest_drawdowns
			WHERE config_id = ?
			ORDER BY rank ASC
		`
		ddRows, err := db.Query(drawdownQuery, bt.Config.ID)
		if err != nil {
			return nil, err
		}

		for ddRows.Next() {
			var dd Drawdown
			err := ddRows.Scan(&dd.Rank, &dd.Drawdown, &dd.PeakDate, &dd.TroughDate, &dd.RecoveryDate, &dd.DurationMonths)
			if err != nil {
				ddRows.Close()
				return nil, err
			}
			bt.Drawdowns = append(bt.Drawdowns, dd)
		}
		ddRows.Close()

		// Load rolling returns for this backtest
		rollingQuery := `
			SELECT period_years, best_cagr, best_start_date, best_end_date,
			       worst_cagr, worst_start_date, worst_end_date
			FROM backtest_rolling_returns
			WHERE config_id = ?
			ORDER BY period_years ASC
		`
		rrRows, err := db.Query(rollingQuery, bt.Config.ID)
		if err != nil {
			return nil, err
		}

		for rrRows.Next() {
			var rr RollingReturn
			err := rrRows.Scan(&rr.PeriodYears, &rr.BestCAGR, &rr.BestStartDate, &rr.BestEndDate,
				&rr.WorstCAGR, &rr.WorstStartDate, &rr.WorstEndDate)
			if err != nil {
				rrRows.Close()
				return nil, err
			}
			bt.RollingReturns = append(bt.RollingReturns, rr)
		}
		rrRows.Close()

		backtests = append(backtests, bt)
	}

	return backtests, nil
}

func getBacktestDetail(strategyName, variant string) (*BacktestDetail, error) {
	// Get config and metrics
	query := `
		SELECT 
			c.id, c.strategy_name, c.variant, c.universe_etfs, 
			c.start_date, c.end_date, c.initial_capital, c.rebalance_frequency,
			c.top_n, c.description,
			m.period_start, m.period_end, m.years,
			m.pre_tax_cagr, m.after_tax_cagr, m.tax_drag,
			m.pre_tax_final, m.after_tax_final, m.total_taxes,
			m.effective_tax_rate, m.max_drawdown, m.max_dd_peak_date,
			m.max_dd_trough_date, m.max_dd_recovery_date, m.max_dd_duration_months,
			m.num_transactions
		FROM backtest_configs c
		JOIN backtest_metrics m ON c.id = m.config_id
		WHERE c.strategy_name = ? AND c.variant = ?
	`

	var detail BacktestDetail
	err := db.QueryRow(query, strategyName, variant).Scan(
		&detail.Config.ID, &detail.Config.StrategyName, &detail.Config.Variant, &detail.Config.UniverseETFs,
		&detail.Config.StartDate, &detail.Config.EndDate, &detail.Config.InitialCapital, &detail.Config.RebalanceFrequency,
		&detail.Config.TopN, &detail.Config.Description,
		&detail.Metrics.PeriodStart, &detail.Metrics.PeriodEnd, &detail.Metrics.Years,
		&detail.Metrics.PreTaxCAGR, &detail.Metrics.AfterTaxCAGR, &detail.Metrics.TaxDrag,
		&detail.Metrics.PreTaxFinal, &detail.Metrics.AfterTaxFinal, &detail.Metrics.TotalTaxes,
		&detail.Metrics.EffectiveTaxRate, &detail.Metrics.MaxDrawdown, &detail.Metrics.MaxDDPeakDate,
		&detail.Metrics.MaxDDTroughDate, &detail.Metrics.MaxDDRecoveryDate, &detail.Metrics.MaxDDDurationMonths,
		&detail.Metrics.NumTransactions,
	)
	if err != nil {
		return nil, err
	}

	// Get annual returns
	annualQuery := `
		SELECT year, pre_tax_return, after_tax_return, tax_drag, pre_tax_end, after_tax_end
		FROM backtest_annual_returns
		WHERE config_id = ?
		ORDER BY year DESC
	`
	rows, err := db.Query(annualQuery, detail.Config.ID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	for rows.Next() {
		var ar AnnualReturn
		err := rows.Scan(&ar.Year, &ar.PreTaxReturn, &ar.AfterTaxReturn, &ar.TaxDrag, &ar.PreTaxEnd, &ar.AfterTaxEnd)
		if err != nil {
			return nil, err
		}
		detail.AnnualReturns = append(detail.AnnualReturns, ar)
	}

	// Get monthly returns (all data for charts)
	monthlyQuery := `
		SELECT date, pre_tax_value, after_tax_value, pre_tax_return, after_tax_return,
		       tax_paid_cumulative, cash_weight, holdings, num_holdings
		FROM backtest_monthly_returns
		WHERE config_id = ?
		ORDER BY date DESC
	`
	rows, err = db.Query(monthlyQuery, detail.Config.ID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	for rows.Next() {
		var mr MonthlyReturn
		err := rows.Scan(&mr.Date, &mr.PreTaxValue, &mr.AfterTaxValue, &mr.PreTaxReturn, &mr.AfterTaxReturn,
			&mr.TaxPaidCumulative, &mr.CashWeight, &mr.Holdings, &mr.NumHoldings)
		if err != nil {
			return nil, err
		}
		detail.MonthlyReturns = append(detail.MonthlyReturns, mr)
	}

	// Get drawdowns
	drawdownQuery := `
		SELECT rank, drawdown, peak_date, trough_date, recovery_date, duration_months
		FROM backtest_drawdowns
		WHERE config_id = ?
		ORDER BY rank ASC
	`
	rows, err = db.Query(drawdownQuery, detail.Config.ID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	for rows.Next() {
		var dd Drawdown
		err := rows.Scan(&dd.Rank, &dd.Drawdown, &dd.PeakDate, &dd.TroughDate, &dd.RecoveryDate, &dd.DurationMonths)
		if err != nil {
			return nil, err
		}
		detail.Drawdowns = append(detail.Drawdowns, dd)
	}

	// Get rolling returns
	rollingQuery := `
		SELECT period_years, best_cagr, best_start_date, best_end_date,
		       worst_cagr, worst_start_date, worst_end_date
		FROM backtest_rolling_returns
		WHERE config_id = ?
		ORDER BY period_years ASC
	`
	rows, err = db.Query(rollingQuery, detail.Config.ID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	for rows.Next() {
		var rr RollingReturn
		err := rows.Scan(&rr.PeriodYears, &rr.BestCAGR, &rr.BestStartDate, &rr.BestEndDate,
			&rr.WorstCAGR, &rr.WorstStartDate, &rr.WorstEndDate)
		if err != nil {
			return nil, err
		}
		detail.RollingReturns = append(detail.RollingReturns, rr)
	}

	detail.Version = Version
	return &detail, nil
}

// HTTP Handlers for backtest pages

func backtestsIndexHandler(w http.ResponseWriter, r *http.Request) {
	summaries, err := getAllBacktestSummaries()
	if err != nil {
		log.Printf("Error fetching backtest summaries: %v", err)
		http.Error(w, "Error loading backtest data", http.StatusInternalServerError)
		return
	}

	data := struct {
		Summaries []BacktestSummary
		Version   string
	}{
		Summaries: summaries,
		Version:   Version,
	}

	err = templates.ExecuteTemplate(w, "backtests.html", data)
	if err != nil {
		log.Printf("Template error: %v", err)
		http.Error(w, "Error rendering template", http.StatusInternalServerError)
	}
}

func backtestDetailHandler(w http.ResponseWriter, r *http.Request) {
	// Parse strategy and variant from URL query params
	strategyName := r.URL.Query().Get("strategy")
	variant := r.URL.Query().Get("variant")

	if strategyName == "" || variant == "" {
		http.Error(w, "Missing strategy or variant parameter", http.StatusBadRequest)
		return
	}

	detail, err := getBacktestDetail(strategyName, variant)
	if err != nil {
		log.Printf("Error fetching backtest detail: %v", err)
		http.Error(w, "Backtest not found", http.StatusNotFound)
		return
	}

	err = templates.ExecuteTemplate(w, "backtest_detail.html", detail)
	if err != nil {
		log.Printf("Template error: %v", err)
		http.Error(w, "Error rendering template", http.StatusInternalServerError)
	}
}
