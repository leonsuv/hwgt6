package de.saigak.opelbridge

import android.Manifest
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.View
import android.widget.Button
import android.widget.EditText
import android.widget.TextView
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import java.net.Inet4Address
import java.net.NetworkInterface

/**
 * Bedienoberflaeche der Bruecke: anmelden, Dienst starten, Adresse fuer die
 * Uhr anzeigen.
 */
class MainActivity : ComponentActivity() {

    private lateinit var store: Store
    private val handler = Handler(Looper.getMainLooper())

    private lateinit var statusText: TextView
    private lateinit var accountText: TextView
    private lateinit var urlText: TextView
    private lateinit var tokenText: TextView
    private lateinit var errorText: TextView
    private lateinit var countryInput: EditText
    private lateinit var toggleButton: Button
    private lateinit var loginButton: Button

    private val ticker = object : Runnable {
        override fun run() {
            render()
            handler.postDelayed(this, 2000)
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        Brands.load(this)
        store = Store(this)
        setContentView(R.layout.activity_main)

        statusText = findViewById(R.id.statusText)
        accountText = findViewById(R.id.accountText)
        urlText = findViewById(R.id.urlText)
        tokenText = findViewById(R.id.tokenText)
        errorText = findViewById(R.id.errorText)
        countryInput = findViewById(R.id.countryInput)
        toggleButton = findViewById(R.id.toggleButton)
        loginButton = findViewById(R.id.loginButton)

        countryInput.setText(store.country)

        loginButton.setOnClickListener {
            val country = countryInput.text.toString().trim().uppercase()
            if (!Brands.has(country)) {
                toast("Land $country unbekannt")
                return@setOnClickListener
            }
            store.country = country
            startActivity(Intent(this, LoginActivity::class.java))
        }

        toggleButton.setOnClickListener {
            if (BridgeService.running) {
                BridgeService.stop(this)
            } else {
                if (!store.loggedIn) {
                    toast("Zuerst anmelden")
                    return@setOnClickListener
                }
                askNotificationPermission()
                BridgeService.start(this)
            }
            handler.postDelayed({ render() }, 600)
        }

        findViewById<Button>(R.id.refreshButton).setOnClickListener {
            if (!BridgeService.running) {
                toast("Dienst laeuft nicht")
            } else {
                BridgeService.refresh(this)
                toast("Fahrzeug wird abgefragt")
            }
        }

        findViewById<Button>(R.id.copyButton).setOnClickListener { copyConfig() }

        findViewById<Button>(R.id.logoutButton).setOnClickListener {
            BridgeService.stop(this)
            store.logout()
            toast("Abgemeldet")
            render()
        }

        // Nach dem ersten Login von selbst starten
        if (store.loggedIn && store.autostart && !BridgeService.running) {
            askNotificationPermission()
            BridgeService.start(this)
        }
    }

    override fun onResume() {
        super.onResume()
        handler.post(ticker)
    }

    override fun onPause() {
        handler.removeCallbacks(ticker)
        super.onPause()
    }

    // ------------------------------------------------------------ Anzeige
    private fun render() {
        val running = BridgeService.running
        statusText.text = if (running) {
            "Bruecke laeuft\n${BridgeService.lastMessage}"
        } else {
            "Bruecke gestoppt"
        }
        toggleButton.text = if (running) "Bruecke stoppen" else "Bruecke starten"

        accountText.text = if (store.loggedIn) {
            "Angemeldet (${store.country})" +
                (store.vehicleName?.let { "\nFahrzeug: $it" } ?: "")
        } else {
            "Nicht angemeldet"
        }
        loginButton.text = if (store.loggedIn) "Neu anmelden" else "Bei Opel anmelden"

        val port = store.port
        val lan = localIp()
        urlText.text = buildString {
            append("http://127.0.0.1:").append(port)
            if (lan != null) append("\noder  http://").append(lan).append(":").append(port)
        }
        tokenText.text = store.watchToken

        val error = store.lastError
        errorText.text = error ?: ""
        errorText.visibility = if (error.isNullOrBlank()) View.GONE else View.VISIBLE
    }

    /** Zeile fuer die Zwischenablage, passend fuer common/config.js der Uhr. */
    private fun copyConfig() {
        val text = "BASE_URL: 'http://127.0.0.1:${store.port}',\n" +
            "TOKEN: '${store.watchToken}',"
        val clipboard = getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
        clipboard.setPrimaryClip(ClipData.newPlainText("config.js", text))
        toast("In die Zwischenablage kopiert")
    }

    /** Erste IPv4-Adresse im WLAN - als Alternative zu 127.0.0.1. */
    private fun localIp(): String? {
        try {
            for (netInterface in NetworkInterface.getNetworkInterfaces()) {
                if (!netInterface.isUp || netInterface.isLoopback) continue
                for (address in netInterface.inetAddresses) {
                    if (address is Inet4Address && !address.isLoopbackAddress) {
                        return address.hostAddress
                    }
                }
            }
        } catch (e: Exception) {
            // ohne Netz gibt es eben keine Adresse
        }
        return null
    }

    private fun askNotificationPermission() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            val granted = ContextCompat.checkSelfPermission(
                this, Manifest.permission.POST_NOTIFICATIONS
            ) == PackageManager.PERMISSION_GRANTED
            if (!granted) {
                ActivityCompat.requestPermissions(
                    this, arrayOf(Manifest.permission.POST_NOTIFICATIONS), 1
                )
            }
        }
    }

    private fun toast(text: String) {
        Toast.makeText(this, text, Toast.LENGTH_SHORT).show()
    }
}
