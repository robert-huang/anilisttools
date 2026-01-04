# Load ggplot2
library(ggplot2)
library(tidyverse)
library(googlesheets4)

gs4_deauth()

ss <- "1x1fLpOOIlRvxBqLGFWpXX9JNDlA5U6JDbF9hY8Uunjs"
sheet <- "manga"
# sheet <- "anime"
data <- read_sheet(ss=ss, sheet=sheet)

# Convert datetime to POSIXct
data$datetime <- as.POSIXct(data$datetime, "", "%Y-%m-%d %H%M%OS")

# ggplot with regression line
ggplot(data, aes(x = datetime, y = mean_score)) +
  geom_point(color = "blue") +
  geom_smooth(method = "lm", color = "red", size = 0.5) +
  labs(title = "Datetime vs Y with Regression Line") +
  scale_y_continuous(limits=c(0,NA)) +
  scale_x_datetime(
    name = "Datetime",
    breaks = seq(min(data$datetime), max(data$datetime), by = "3 months"),  # Adjust interval here
    labels = scales::date_format("%Y-%m-%d")  # Change the date-time format
  ) +
  theme_minimal() +
  theme(axis.text.x = element_text(angle = 45, hjust = 1))

# Reshape the data into a "long" format for ggplot2
df_long <- data %>%
  pivot_longer(cols = c(total_count, num_count, value2, mean_score, std),  # These are the columns to plot
               names_to = "variable",                                      # New column 'variable'
               values_to = "value")                                        # New column 'value'

# Create the ggplot with faceting
ggplot(df_long, aes(x = datetime, y = value, color = variable)) +
  geom_point() +                         # Add points
  geom_line() +                          # Add lines
  facet_wrap(~ variable, scales = "free_y") +  # Separate panels for each variable
  labs(title = "Multiple Y-Variables over Time",
       x = "Datetime", y = "Value") +
  theme_minimal() + 
  theme(axis.text.x = element_text(angle = 45, hjust = 1))  # Rotate x-axis labels for readability

data_long <- data %>%
  select(datetime, total_count, num_count, value2, mean_score, std) %>%
  gather(key = "variable", value = "value", -datetime)

# Create the plot
ggplot(data_long, aes(x = datetime, y = value, color = variable)) +
  geom_line() +
  scale_y_continuous(name = "Values") +
  labs(title = "Multiple Y Variables with Different Min/Max", 
       x = "Datetime", 
       y = "Scaled Value") +
  theme_minimal() +
  theme(axis.text.x = element_text(angle = 45, hjust = 1)) +
  scale_color_manual(values = c("total_count" = "blue", "num_count" = "red", 
                                "value2" = "green", "mean_score" = "purple", "std" = "orange"))

ggplot(data, aes(x = datetime)) +
  # geom_line(aes(y = total_count, color = "Total Count"), size = 1) +
  # geom_line(aes(y = num_count / 60, color = "Num Count"), size = 1) + # Dividing to match scale with primary axis
  # geom_line(aes(y = value2, color = "Value2"), size = 1) +
  geom_line(aes(y = mean_score, color = "Mean Score"), size = 1) +
  geom_line(aes(y = std, color = "Standard Deviation"), size = 1) +
  
  # Customizing the Y axis scale and adding a secondary axis
  scale_y_continuous(name = "Total Count / Value2", limits = c(0, NA),
                     sec.axis = sec_axis(~ . * 60, name = "Num Count")) +

  scale_x_datetime(
    name = "Datetime",
    breaks = seq(min(data$datetime), max(data$datetime), by = "3 months"),  # Adjust interval here
    labels = scales::date_format("%Y-%m-%d")  # Change the date-time format
  ) +

  # geom_smooth(aes(y = total_count, color = "Total Count Trend"), method = "lm", se = FALSE, linetype = "dashed", size = 1) +
  # geom_smooth(aes(y = num_count / 60, color = "Num Count Trend"), method = "lm", se = FALSE, linetype = "dashed", size = 1) + # Trend for num_count
  # geom_smooth(aes(y = value2, color = "Value2 Trend"), method = "lm", se = FALSE, linetype = "dashed", size = 1) +
  geom_smooth(aes(y = mean_score, color = "Mean Score Trend"), method = "lm", se = FALSE, linetype = "dashed", size = 1) +
  geom_smooth(aes(y = std, color = "Standard Deviation Trend"), method = "lm", se = FALSE, linetype = "dashed", size = 1) +

  labs(title = "Multiple Y Variables on Same Plot", 
       x = "Datetime", 
       color = "Legend") +
  theme_minimal() +
  theme(axis.text.x = element_text(angle = 45, hjust = 1)) +
  scale_color_manual(values = c("Total Count" = "blue", "Num Count" = "red", 
                                "Value2" = "green", "Mean Score" = "purple", "Standard Deviation" = "orange"))

