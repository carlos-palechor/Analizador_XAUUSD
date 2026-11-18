#property script_show_inputs
#property strict

input string TargetSymbol = "XAUUSDm";
input string OutputFile = "xau_collector_symbol_sessions.csv";

// Escribe todas las sesiones de cotización o negociación de un día según la información del terminal.
void WriteSessions(const int file_handle, const string symbol_name, const ENUM_DAY_OF_WEEK day,
                   const bool trade_sessions)
  {
   for(uint session_index = 0; ; session_index++)
     {
      datetime starts_at = 0;
      datetime ends_at = 0;
      bool found = false;
      string session_kind = "QUOTE";
      if(trade_sessions)
        {
         found = SymbolInfoSessionTrade(symbol_name, day, session_index, starts_at, ends_at);
         session_kind = "TRADE";
        }
      else
         found = SymbolInfoSessionQuote(symbol_name, day, session_index, starts_at, ends_at);
      if(!found)
         break;

      FileWrite(
         file_handle,
         "2",
         symbol_name,
         session_kind,
         EnumToString(day),
         (string)session_index,
         (string)((long)starts_at % 86400),
         (string)((long)ends_at % 86400),
         TimeToString(TimeGMT(), TIME_DATE | TIME_SECONDS),
         TimeToString(TimeTradeServer(), TIME_DATE | TIME_SECONDS)
      );
     }
  }

// Consulta al terminal MT5 y exporta las sesiones semanales reales del símbolo seleccionado.
void OnStart()
  {
   if(!SymbolSelect(TargetSymbol, true))
     {
      Print("No fue posible seleccionar el símbolo: ", TargetSymbol);
      return;
     }

   int file_handle = FileOpen(OutputFile, FILE_WRITE | FILE_CSV | FILE_ANSI, ';');
   if(file_handle == INVALID_HANDLE)
     {
      Print("No fue posible crear el archivo de sesiones. Error: ", GetLastError());
      return;
     }

   FileWrite(
      file_handle,
      "schema_version",
      "symbol",
      "session_kind",
      "weekday",
      "session_index",
      "start_seconds_server",
      "end_seconds_server",
      "generated_at_utc",
      "server_time"
   );

   for(int day = SUNDAY; day <= SATURDAY; day++)
     {
      ENUM_DAY_OF_WEEK weekday = (ENUM_DAY_OF_WEEK)day;
      WriteSessions(file_handle, TargetSymbol, weekday, false);
      WriteSessions(file_handle, TargetSymbol, weekday, true);
     }

   FileClose(file_handle);
   Print("Sesiones exportadas: ", OutputFile);
  }
