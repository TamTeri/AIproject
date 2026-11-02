workspace "EventHub" "EventHub C4 model before and after Calls 3, 4 and 5" {

    !identifiers hierarchical

    model {
        buyer = person "Buyer" "Registers, browses events, buys tickets in a chosen currency, and reopens past orders."
        tester = person "QA / developer" "Runs the system tests with one command (or the GitHub button) and reads the report." {
            tags "PostCall5"
        }
        administrator = person "Administrator" "Finance or EventHub staff who update exchange rates and read the purchase-attempt audit log. How an account becomes an administrator is an open decision." {
            tags "Administrator"
        }

        eventHub = softwareSystem "EventHub" "Public ticketing website for events, with student discounts and multi-currency pricing." {

            webApp = container "Flask web application" "Single Python/Flask application (modular monolith). Server-rendered HTML pages; one Flask blueprint per component; components call each other through Python service interfaces." "Python 3, Flask, SQLAlchemy" {

                identity = component "Identity" "Registration, login, password hashing, sessions, order ownership checks." "Flask blueprint /auth + IdentityService"
                catalog = component "Catalog" "Event list, artist and venue search, event pages with availability." "Flask blueprint /events + CatalogService"
                purchase = component "Purchase" "Checkout flow: validates quantity and currency on the server, runs the simulated payment step, creates the order." "Flask blueprint /checkout + PurchaseService"
                pricing = component "Pricing" "Computes the price: base price x quantity, discount eligibility, currency conversion, total." "PricingService (Python module)"
                inventory = component "Inventory" "Fixed capacity per event, availability, checkout holds, atomic check-and-decrement." "InventoryService (Python module)"
                orders = component "Orders" "Order history and confirmation-style order pages, scoped to the signed-in buyer." "Flask blueprint /orders + OrderService"
                audit = component "Audit" "Records every purchase attempt and its outcome." "AuditService (Python module)"
                eligibility = component "Discount eligibility" "One small function: normalizes the buyer email and decides student-discount eligibility. Open policy questions (plus addresses, subdomains, verification) change only here." "evaluate_student_eligibility() (Python module)" {
                    tags "PostCall4"
                }

                group "Administrator-only area" {
                    admin = component "Administration" "Rate-management screen and purchase-attempt audit viewer. Every route requires the administrator role; no buyer-facing component calls it." "Flask blueprint /admin" {
                        tags "AdministratorOnly"
                    }
                }
            }

            systemTests = container "System test suite" "Selenium drives a real browser through every buyer and admin journey; each test names the requirement it proves. Runs with one command and on every code change, and writes an HTML report." "Python, pytest, Selenium, headless Chrome" {
                tags "PostCall5" "TestTooling"
            }

            database = container "EventHub database" "All persistent application data: accounts, events, inventory, orders, purchase-attempt records." "PostgreSQL" {
                tags "Database"
            }
        }

        # ---- System and container level (declared first so they are the labels shown on higher-level views)
        buyer -> eventHub "Browses events, buys tickets, views orders" "HTTPS"
        administrator -> eventHub "Updates exchange rates, reads audit log" "HTTPS"
        buyer -> eventHub.webApp "Browses events, buys tickets, views orders" "HTTPS (HTML pages)"
        administrator -> eventHub.webApp "Updates exchange rates, reads audit log" "HTTPS (HTML pages, /admin)"
        eventHub.webApp -> eventHub.database "Reads and writes all persistent data in ACID transactions" "SQL over TCP (SQLAlchemy / psycopg)"

        # ---- People to components
        buyer -> eventHub.webApp.identity "Registers, logs in, logs out" "HTTPS /auth"
        buyer -> eventHub.webApp.catalog "Browses and searches events" "HTTPS /events"
        buyer -> eventHub.webApp.purchase "Selects quantity and currency, checks out" "HTTPS /checkout"
        buyer -> eventHub.webApp.orders "Views order history and confirmations" "HTTPS /orders"
        administrator -> eventHub.webApp.identity "Logs in" "HTTPS /auth/login"
        administrator -> eventHub.webApp.admin "Edits rates, opens audit viewer" "HTTPS /admin"

        # ---- Purchase path
        eventHub.webApp.purchase -> eventHub.webApp.identity "current_buyer()" "Python call"
        eventHub.webApp.purchase -> eventHub.webApp.catalog "get_event()" "Python call"
        eventHub.webApp.purchase -> eventHub.webApp.pricing "quote()" "Python call"
        eventHub.webApp.purchase -> eventHub.webApp.inventory "hold() / commit(): atomic" "Python call"
        eventHub.webApp.purchase -> eventHub.webApp.audit "record_attempt()" "Python call"
        eventHub.webApp.purchase -> eventHub.webApp.orders "create_order()" "Python call"

        # ---- Other component interactions
        eventHub.webApp.catalog -> eventHub.webApp.inventory "available()" "Python call"
        eventHub.webApp.orders -> eventHub.webApp.identity "require_login(), owner check" "Python call"
        eventHub.webApp.admin -> eventHub.webApp.identity "require_admin()" "Python call" {
            tags "PostCall3"
        }
        eventHub.webApp.admin -> eventHub.webApp.pricing "list_rates(), set_rate()" "Python call"
        eventHub.webApp.admin -> eventHub.webApp.audit "query_attempts()" "Python call"

        # ---- Components to database
        eventHub.webApp.identity -> eventHub.database "accounts, sessions" "SQL"
        eventHub.webApp.catalog -> eventHub.database "events" "SQL"
        eventHub.webApp.pricing -> eventHub.database "exchange_rates" "SQL" {
            tags "PostCall3"
        }
        eventHub.webApp.inventory -> eventHub.database "conditional UPDATE, holds" "SQL"
        eventHub.webApp.orders -> eventHub.database "orders" "SQL"
        eventHub.webApp.audit -> eventHub.database "purchase_attempts (append-only)" "SQL"

        # ---- After Call 4: implementation decisions
        eventHub.webApp.pricing -> eventHub.webApp.eligibility "is_eligible(email)" "Python call" {
            tags "PostCall4"
        }
        buyer -> eventHub.webApp.catalog "Double-clicks an event card (Quick Buy)" "HTTPS POST /events/{id}/quick-buy" {
            tags "PostCall4"
        }
        eventHub.webApp.catalog -> eventHub.webApp.purchase "quick_buy(): same purchase path" "Python call" {
            tags "PostCall4"
        }
        eventHub.webApp.identity -> eventHub.database "account_sessions (hashed tokens, idle timeout)" "SQL" {
            tags "PostCall4"
        }
        eventHub.webApp.purchase -> eventHub.database "One transaction per attempt; SELECT ... FOR UPDATE on the event" "SQL" {
            tags "PostCall4"
        }

        # ---- After Call 5: testing, security findings and requirement gaps
        tester -> eventHub.systemTests "Runs at the press of a button; reads the pass/fail report" "run-system-tests.cmd / GitHub Actions" {
            tags "PostCall5"
        }
        eventHub.systemTests -> eventHub.webApp "Drives a real browser through the journeys (Selenium WebDriver)" "HTTP" {
            tags "PostCall5"
        }
        eventHub.systemTests -> eventHub.database "Resets and seeds a throwaway copy; fast-forwards hold and session time" "SQL" {
            tags "PostCall5"
        }
        eventHub.webApp.purchase -> eventHub.database "idempotency_records: one-time form keys (a double click buys once)" "SQL" {
            tags "PostCall5"
        }
        eventHub.webApp.purchase -> eventHub.database "purchase_rate_windows: 10 purchase requests per account per minute" "SQL" {
            tags "PostCall5"
        }
        eventHub.webApp.purchase -> eventHub.webApp.pricing "discount_still_applies(): re-check the current email at payment" "Python call" {
            tags "PostCall5"
        }
        buyer -> eventHub.webApp.identity "Changes email (needs current password); picks a home currency" "HTTPS /account, /register" {
            tags "PostCall5"
        }
    }

    views {
        # Before Call 3: views built from Calls 1 and 2 only (one actor, no admin area).
        systemContext eventHub "Context_PreCall3" {
            include *
            exclude "relationship.tag==PostCall3"
            exclude "relationship.tag==PostCall5"
            exclude "element.tag==PostCall5"
            exclude "relationship.tag==PostCall4"
            exclude administrator
            autolayout lr
            title "EventHub system context - before Call 3"
        }

        container eventHub "Container_PreCall3" {
            include *
            exclude "relationship.tag==PostCall3"
            exclude "relationship.tag==PostCall5"
            exclude "element.tag==PostCall5"
            exclude "relationship.tag==PostCall4"
            exclude administrator
            autolayout lr
            title "EventHub containers - before Call 3"
        }

        component eventHub.webApp "Component_PreCall3" {
            include *
            exclude "relationship.tag==PostCall3"
            exclude "relationship.tag==PostCall4"
            exclude "relationship.tag==PostCall5"
            exclude "element.tag==PostCall5"
            exclude "element.tag==PostCall4"
            exclude administrator
            exclude eventHub.webApp.admin
            autolayout lr 250 200
            title "Flask application components - before Call 3"
        }

        # After Call 3: administrator actor, admin routes, Administration component.
        systemContext eventHub "Context_PostCall3" {
            include *
            exclude "relationship.tag==PostCall5"
            exclude "element.tag==PostCall5"
            exclude "relationship.tag==PostCall4"
            autolayout lr
            title "EventHub system context - after Call 3"
        }

        container eventHub "Container_PostCall3" {
            include *
            exclude "relationship.tag==PostCall5"
            exclude "element.tag==PostCall5"
            exclude "relationship.tag==PostCall4"
            autolayout lr
            title "EventHub containers - after Call 3"
        }

        component eventHub.webApp "Component_PostCall3" {
            include *
            exclude "relationship.tag==PostCall4"
            exclude "relationship.tag==PostCall5"
            exclude "element.tag==PostCall5"
            exclude "element.tag==PostCall4"
            autolayout lr 250 200
            title "Flask application components - after Call 3"
        }

        # After Call 4: separate eligibility function, quick-buy path, server-side sessions.
        component eventHub.webApp "Component_PostCall4" {
            include *
            exclude "relationship.tag==PostCall5"
            exclude "element.tag==PostCall5"
            autolayout lr 250 200
            title "Flask application components - after Call 4 (as built)"
        }

        # After Call 5: one-time form keys, request limit, discount re-check at
        # payment, email change, and the Selenium system test suite.
        container eventHub "Container_PostCall5" {
            include *
            autolayout lr
            title "EventHub containers - after Call 5 (with the system test suite)"
        }

        component eventHub.webApp "Component_PostCall5" {
            include *
            exclude eventHub.systemTests
            exclude tester
            autolayout lr 250 200
            title "Flask application components - after Call 5 (as built)"
        }


        styles {
            element "Person" {
                shape person
                background #08415c
                color #ffffff
            }
            element "Software System" {
                background #13795b
                color #ffffff
            }
            element "Container" {
                background #198754
                color #ffffff
            }
            element "Component" {
                background #4f9d69
                color #ffffff
            }
            element "Database" {
                shape cylinder
                background #6c757d
                color #ffffff
            }
            element "Administrator" {
                background #8f2d56
                color #ffffff
            }
            element "AdministratorOnly" {
                background #b56576
                color #ffffff
            }
            element "Group" {
                color #8f2d56
            }
            element "TestTooling" {
                background #5c4d7d
                color #ffffff
            }
        }
    }
}
