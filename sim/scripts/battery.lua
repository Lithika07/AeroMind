--[[
  Simulated 6S LiPo for the Hexa-X, fed to ArduPilot's scripting battery backend (BATT_MONITOR 29).

  SITL over JSON simulates no battery, so this script supplies one from the motor outputs:

    current = AVIONICS_A + HOVER_A * mean_i((t_i / HOVER_T)^3)

  where t_i is motor i's output (0..1 over 1100..1900 us). The rotors are velocity-controlled
  (speed proportional to t), thrust goes with speed squared and shaft power with speed cubed, so
  at hover the six motors draw HOVER_A together. Voltage is the cells' open-circuit voltage at the
  current state of charge, minus the sag across the pack's internal resistance.

  The backend integrates consumed mAh itself (consumed_mah left NaN) and reports remaining
  percent from BATT_CAPACITY, so a smaller BATT_CAPACITY is a smaller battery. MAV_CMD_BATTERY_RESET
  refills it between flights.

  These constants are a model, not measurements of the real pack.
--]]

local BATTERY_INDEX = 0
local CELLS = 6
local AVIONICS_A = 1.5        -- flight controller, companion computer, sensors
local HOVER_A = 19.0          -- 2.55 kg hexacopter, ~420 W at 22.2 V
local HOVER_T = 0.534         -- motor output at hover: 1527 us in a 30 m SITL hover
local RESISTANCE_OHM = 0.012  -- whole pack
local MOTOR_FUNCTIONS = {33, 34, 35, 36, 37, 38}
local PWM_MIN = 1100
local PWM_MAX = 1900
local UPDATE_MS = 100

-- open-circuit voltage per cell against state of charge (0..1), typical LiPo curve
local OCV_SOC = {0.00, 0.05, 0.10, 0.20, 0.40, 0.60, 0.80, 0.90, 1.00}
local OCV_V   = {3.27, 3.50, 3.61, 3.70, 3.78, 3.86, 3.98, 4.08, 4.20}

local function cell_ocv(soc)
  if soc <= OCV_SOC[1] then return OCV_V[1] end
  for i = 2, #OCV_SOC do
    if soc <= OCV_SOC[i] then
      local f = (soc - OCV_SOC[i - 1]) / (OCV_SOC[i] - OCV_SOC[i - 1])
      return OCV_V[i - 1] + f * (OCV_V[i] - OCV_V[i - 1])
    end
  end
  return OCV_V[#OCV_V]
end

local function motor_current()
  local load = 0
  for _, fn in ipairs(MOTOR_FUNCTIONS) do
    local pwm = SRV_Channels:get_output_pwm(fn)
    if pwm then
      local t = math.max(0, math.min(1, (pwm - PWM_MIN) / (PWM_MAX - PWM_MIN)))
      load = load + (t / HOVER_T) ^ 3
    end
  end
  return HOVER_A * load / #MOTOR_FUNCTIONS
end

local function state_of_charge()
  local capacity = param:get('BATT_CAPACITY') or 0
  local consumed = battery:consumed_mah(BATTERY_INDEX)
  if capacity <= 0 or not consumed then
    return 1.0
  end
  return math.max(0, 1 - consumed / capacity)
end

local function update()
  local amps = AVIONICS_A
  if arming:is_armed() then
    amps = amps + motor_current()
  end
  local volts = CELLS * cell_ocv(state_of_charge()) - amps * RESISTANCE_OHM
  local state = BattMonitorScript_State()
  state:healthy(true)
  state:voltage(volts)
  state:cell_count(CELLS)
  state:current_amps(amps)
  battery:handle_scripting(BATTERY_INDEX, state)
  return update, UPDATE_MS
end

gcs:send_text(6, 'battery.lua: simulated 6S pack running')
return update, UPDATE_MS
