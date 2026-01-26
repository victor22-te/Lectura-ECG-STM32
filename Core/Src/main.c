#include "main.h"
#include <stdint.h>

/* ================= CONFIGURACIÓN ================= */

#define SYSTEM_CLOCK_FREQ   84000000UL
#define ADC_SAMPLE_RATE     250
#define USART_BAUDRATE      115200

#define ECG_ADC_CHANNEL     0   // PA0
#define LO_PLUS_PIN         1   // PA1
#define LO_MINUS_PIN        4   // PA4

#define AVG_SAMPLES         8   // Reducido para mejor respuesta

/* ================= COEFICIENTES DE FILTROS ================= */
/*
 * Filtro Pasa-Bajas Butterworth 2do orden
 * Frecuencia de corte: 40Hz @ Fs=250Hz
 * Elimina ruido de alta frecuencia
 */
#define LP_B0  0.2066f
#define LP_B1  0.4131f
#define LP_B2  0.2066f
#define LP_A1 -0.3695f
#define LP_A2  0.1958f

/*
 * Filtro Pasa-Altas Butterworth 2do orden  
 * Frecuencia de corte: 0.5Hz @ Fs=250Hz
 * Elimina deriva de línea base (DC drift)
 */
#define HP_B0  0.9922f
#define HP_B1 -1.9844f
#define HP_B2  0.9922f
#define HP_A1 -1.9844f
#define HP_A2  0.9845f

/*
 * Filtro Notch 60Hz (para eliminar interferencia de red eléctrica)
 * Q=30, Fs=250Hz
 */
#define NOTCH_B0  0.9651f
#define NOTCH_B1 -0.2347f
#define NOTCH_B2  0.9651f
#define NOTCH_A1 -0.2347f
#define NOTCH_A2  0.9302f

/* ================= PROTOTIPOS ================= */

void SystemClock_Config_84MHz(void);
void GPIO_Init(void);
void ADC1_Init(void);
void USART2_Init(void);
void TIM2_Init(void);

uint16_t ADC1_Read(void);
uint16_t ADC1_ReadFiltered(void);
float LowPassFilter(float input);
float HighPassFilter(float input);
float NotchFilter(float input);
uint8_t Check_LeadOff(void);

void USART2_SendChar(char c);
void USART2_SendString(const char* str);
void USART2_SendNumber(uint16_t num);

/* ================= VARIABLES ================= */

volatile uint8_t sample_ready = 0;

/* Variables de estado para filtros IIR */
static float lp_x1 = 0, lp_x2 = 0;
static float lp_y1 = 0, lp_y2 = 0;

static float hp_x1 = 0, hp_x2 = 0;
static float hp_y1 = 0, hp_y2 = 0;

static float notch_x1 = 0, notch_x2 = 0;
static float notch_y1 = 0, notch_y2 = 0;

/* ================= MAIN ================= */

int main(void)
{
    HAL_Init();
    SystemClock_Config_84MHz();

    GPIO_Init();
    ADC1_Init();
    USART2_Init();
    TIM2_Init();

    USART2_SendString("\r\nECG AD8232 STM32F401 OK\r\n");

    while (1)
    {
        if (sample_ready)
        {
            sample_ready = 0;

            if (!Check_LeadOff())
            {
                uint16_t ecg = ADC1_ReadFiltered();
                USART2_SendNumber(ecg);
                USART2_SendString("\r\n");
            }
            else
            {
                USART2_SendString("LEADS_OFF\r\n");
            }
        }
    }
}

/* ================= CLOCK ================= */

void SystemClock_Config_84MHz(void)
{
    RCC->APB1ENR |= RCC_APB1ENR_PWREN;
    PWR->CR |= PWR_CR_VOS;

    FLASH->ACR = FLASH_ACR_LATENCY_2WS |
                 FLASH_ACR_PRFTEN |
                 FLASH_ACR_ICEN |
                 FLASH_ACR_DCEN;

    RCC->CR |= RCC_CR_HSEON;
    while (!(RCC->CR & RCC_CR_HSERDY));

    RCC->PLLCFGR = (8 << 0) | (336 << 6) | (1 << 16) |
                   (7 << 24) | RCC_PLLCFGR_PLLSRC_HSE;

    RCC->CR |= RCC_CR_PLLON;
    while (!(RCC->CR & RCC_CR_PLLRDY));

    RCC->CFGR |= RCC_CFGR_PPRE1_DIV2;
    RCC->CFGR |= RCC_CFGR_SW_PLL;
    while ((RCC->CFGR & RCC_CFGR_SWS) != RCC_CFGR_SWS_PLL);

    SystemCoreClock = SYSTEM_CLOCK_FREQ;
}

/* ================= GPIO ================= */

void GPIO_Init(void)
{
    RCC->AHB1ENR |= RCC_AHB1ENR_GPIOAEN;

    // PA0 - Analog (ECG signal)
    GPIOA->MODER |= (3 << 0);

    // PA1 - Input with Pull-Down (LO+)
    GPIOA->MODER &= ~(3 << 2);          // Input mode
    GPIOA->PUPDR &= ~(3 << 2);
    GPIOA->PUPDR |= (2 << 2);           // Pull-down

    // PA4 - Input with Pull-Down (LO-)
    GPIOA->MODER &= ~(3 << 8);          // Input mode
    GPIOA->PUPDR &= ~(3 << 8);
    GPIOA->PUPDR |= (2 << 8);           // Pull-down

    // PA2 TX, PA3 RX - USART2 (AF7)
    GPIOA->MODER &= ~((3 << 4) | (3 << 6));
    GPIOA->MODER |= (2 << 4) | (2 << 6);
    GPIOA->AFR[0] |= (7 << 8) | (7 << 12);
}

/* ================= ADC ================= */

void ADC1_Init(void)
{
    RCC->APB2ENR |= RCC_APB2ENR_ADC1EN;

    ADC->CCR |= ADC_CCR_ADCPRE_0; // /4

    ADC1->CR1 = 0;
    ADC1->CR2 = 0;

    ADC1->SQR3 = ECG_ADC_CHANNEL;
    ADC1->SMPR2 |= (7 << 0); // 480 ciclos - más tiempo de muestreo = menos ruido

    ADC1->CR2 |= ADC_CR2_ADON;

    /* Dummy conversion */
    ADC1->CR2 |= ADC_CR2_SWSTART;
    while (!(ADC1->SR & ADC_SR_EOC));
    (void)ADC1->DR;
}

/* Lectura simple del ADC */
uint16_t ADC1_Read(void)
{
    ADC1->CR2 |= ADC_CR2_SWSTART;
    while (!(ADC1->SR & ADC_SR_EOC));
    return ADC1->DR;
}

/* Filtro Pasa-Bajas (elimina ruido de alta frecuencia) */
float LowPassFilter(float input)
{
    float output = LP_B0 * input + LP_B1 * lp_x1 + LP_B2 * lp_x2
                  - LP_A1 * lp_y1 - LP_A2 * lp_y2;
    
    lp_x2 = lp_x1;
    lp_x1 = input;
    lp_y2 = lp_y1;
    lp_y1 = output;
    
    return output;
}

/* Filtro Pasa-Altas (elimina deriva de línea base / DC) */
float HighPassFilter(float input)
{
    float output = HP_B0 * input + HP_B1 * hp_x1 + HP_B2 * hp_x2
                  - HP_A1 * hp_y1 - HP_A2 * hp_y2;
    
    hp_x2 = hp_x1;
    hp_x1 = input;
    hp_y2 = hp_y1;
    hp_y1 = output;
    
    return output;
}

/* Filtro Notch (elimina interferencia de 60Hz de la red eléctrica) */
float NotchFilter(float input)
{
    float output = NOTCH_B0 * input + NOTCH_B1 * notch_x1 + NOTCH_B2 * notch_x2
                  - NOTCH_A1 * notch_y1 - NOTCH_A2 * notch_y2;
    
    notch_x2 = notch_x1;
    notch_x1 = input;
    notch_y2 = notch_y1;
    notch_y1 = output;
    
    return output;
}

/* Lectura del ADC con filtrado completo */
uint16_t ADC1_ReadFiltered(void)
{
    uint32_t sum = 0;

    /* Promedio de muestras (reduce ruido aleatorio) */
    for (int i = 0; i < AVG_SAMPLES; i++)
    {
        sum += ADC1_Read();
    }
    
    float raw_value = (float)(sum / AVG_SAMPLES);
    
    /* Cadena de filtrado:
     * 1. Filtro Notch 60Hz - elimina interferencia de red
     * 2. Filtro Pasa-Bajas 40Hz - suaviza señal, elimina ruido alto
     * 3. Filtro Pasa-Altas 0.5Hz - elimina deriva DC
     */
    float filtered = raw_value;
    filtered = NotchFilter(filtered);
    filtered = LowPassFilter(filtered);
    filtered = HighPassFilter(filtered);
    
    /* Agregar offset DC para mantener señal en rango positivo */
    filtered += 2048.0f;
    
    /* Limitar al rango del ADC */
    if (filtered < 0) filtered = 0;
    if (filtered > 4095) filtered = 4095;

    return (uint16_t)filtered;
}

/* ================= USART ================= */

void USART2_Init(void)
{
    RCC->APB1ENR |= RCC_APB1ENR_USART2EN;

    USART2->BRR = (42000000 + USART_BAUDRATE / 2) / USART_BAUDRATE;
    USART2->CR1 = USART_CR1_TE | USART_CR1_RE;
    USART2->CR1 |= USART_CR1_UE;
}

void USART2_SendChar(char c)
{
    while (!(USART2->SR & USART_SR_TXE));
    USART2->DR = c;
}

void USART2_SendString(const char* str)
{
    while (*str) USART2_SendChar(*str++);
}

void USART2_SendNumber(uint16_t num)
{
    char buf[6];
    int i = 0;

    if (!num) { USART2_SendChar('0'); return; }

    while (num)
    {
        buf[i++] = '0' + (num % 10);
        num /= 10;
    }

    while (i--) USART2_SendChar(buf[i]);
}

/* ================= TIMER ================= */

void TIM2_Init(void)
{
    RCC->APB1ENR |= RCC_APB1ENR_TIM2EN;

    TIM2->PSC = 83;
    TIM2->ARR = 3999;

    TIM2->DIER |= TIM_DIER_UIE;
    NVIC_EnableIRQ(TIM2_IRQn);

    TIM2->CR1 |= TIM_CR1_CEN;
}


/* ================= LEAD OFF ================= */

uint8_t Check_LeadOff(void)
{
    return (GPIOA->IDR & (1 << LO_PLUS_PIN)) ||
           (GPIOA->IDR & (1 << LO_MINUS_PIN));
}
