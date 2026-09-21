package de.saigak.opelbridge

import android.annotation.SuppressLint
import android.graphics.Bitmap
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.webkit.CookieManager
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Button
import android.widget.TextView
import android.widget.Toast
import androidx.activity.ComponentActivity

/**
 * Anmeldung bei MyOpel im eingebetteten Browser.
 *
 * Zwei Wege, genau wie in der Python-Bibliothek:
 *
 *  A) Der Normalfall: nach dem Login leitet die Seite auf
 *     mymopsdk://oauth2redirect/de?code=... um. Im WebView faengt
 *     shouldOverrideUrlLoading diese Adresse ab - kein Abtippen noetig.
 *
 *  B) Die Zustimmungsseite von Opel haengt oefter. Dann liefert der Knopf
 *     unten den Code ueber das Sitzungs-Cookie iPlanetDirectoryPro nach,
 *     das nach dem Login bereits im WebView liegt.
 */
class LoginActivity : ComponentActivity() {

    private lateinit var store: Store
    private lateinit var api: OpelApi
    private lateinit var webView: WebView
    private lateinit var infoText: TextView
    private val handler = Handler(Looper.getMainLooper())

    @Volatile
    private var finishing = false

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        Brands.load(this)
        store = Store(this)
        api = OpelApi(store)
        setContentView(R.layout.activity_login)

        infoText = findViewById(R.id.loginInfo)
        webView = findViewById(R.id.webView)

        findViewById<Button>(R.id.finishButton).setOnClickListener { finishWithCookie() }
        findViewById<Button>(R.id.resetButton).setOnClickListener { clearAndReload() }

        val settings = webView.settings
        settings.javaScriptEnabled = true
        settings.domStorageEnabled = true
        settings.userAgentString = settings.userAgentString      // Standard-Browserkennung behalten
        CookieManager.getInstance().setAcceptCookie(true)
        CookieManager.getInstance().setAcceptThirdPartyCookies(webView, true)

        webView.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(
                view: WebView?, request: WebResourceRequest?
            ): Boolean {
                val url = request?.url?.toString() ?: return false
                return intercept(url)
            }

            @Deprecated("Fuer Android unter API 24")
            override fun shouldOverrideUrlLoading(view: WebView?, url: String?): Boolean {
                return intercept(url ?: return false)
            }

            override fun onPageStarted(view: WebView?, url: String?, favicon: Bitmap?) {
                super.onPageStarted(view, url, favicon)
                if (url != null && url.contains("authorize-consentments")) {
                    infoText.text = getString(R.string.login_consent_hint)
                }
            }
        }

        infoText.text = getString(R.string.login_hint, store.country)
        webView.loadUrl(api.authorizeUrl())
    }

    /** Rueckleitung der App abfangen und den Code einloesen. */
    private fun intercept(url: String): Boolean {
        if (!url.startsWith(Brands.scheme + "://")) return false
        val code = api.extractCode(url)
        if (code == null) {
            toast("Rueckleitung ohne Code")
            return true
        }
        exchange(code)
        return true
    }

    private fun exchange(code: String) {
        if (finishing) return
        finishing = true
        infoText.text = getString(R.string.login_exchanging)
        Thread {
            try {
                api.exchangeCode(code)
                // Fahrzeug direkt bestimmen, damit die Uhr sofort Daten bekommt
                try {
                    api.resolveVehicle()
                } catch (e: Exception) {
                    // Fahrzeugliste kann spaeter nachgeholt werden
                }
                handler.post {
                    toast("Anmeldung erfolgreich")
                    BridgeService.start(this)
                    finish()
                }
            } catch (e: Exception) {
                finishing = false
                handler.post {
                    infoText.text = getString(R.string.login_failed, e.message ?: "unbekannt")
                }
            }
        }.start()
    }

    /** Weg B: Code ueber das vorhandene Sitzungs-Cookie nachholen. */
    private fun finishWithCookie() {
        val cookies = CookieManager.getInstance().getCookie(Brands.oauthUrl)
        val sso = cookies
            ?.split(";")
            ?.map { it.trim() }
            ?.firstOrNull { it.startsWith("iPlanetDirectoryPro=") }
            ?.substringAfter("=")
        if (sso.isNullOrBlank()) {
            infoText.text = getString(R.string.login_no_cookie)
            return
        }
        infoText.text = getString(R.string.login_using_cookie)
        Thread {
            try {
                val code = api.codeFromSsoCookie(sso)
                handler.post { exchange(code) }
            } catch (e: Exception) {
                handler.post {
                    infoText.text = getString(R.string.login_failed, e.message ?: "unbekannt")
                }
            }
        }.start()
    }

    private fun clearAndReload() {
        CookieManager.getInstance().removeAllCookies(null)
        CookieManager.getInstance().flush()
        webView.clearCache(true)
        finishing = false
        infoText.text = getString(R.string.login_hint, store.country)
        webView.loadUrl(api.authorizeUrl())
    }

    override fun onBackPressed() {
        if (webView.canGoBack()) webView.goBack() else super.onBackPressed()
    }

    private fun toast(text: String) {
        Toast.makeText(this, text, Toast.LENGTH_SHORT).show()
    }
}
