library(shiny)
library(shinythemes)

data = read.csv("data.csv", sep = ";")

choices_utilisateur <- c("Tout", unique(data$Utilisateur[!is.na(data$Utilisateur)]))
choices_technicien <- c("Tout", unique(data$Technicien[!is.na(data$Technicien)]))
choices_etat <- c("Tout", unique(data$Etats[!is.na(data$Etats)]))
choices_urgence <- c("Tout", unique(data$Urgence[!is.na(data$Urgence)]))

fluidPage(
  theme = shinytheme("flatly"),
  
  tabsetPanel(
    tabPanel("Analyse des tickets",
             sidebarLayout(
               sidebarPanel(
                 fluidRow(
                   column(12, selectInput("utilisateur", "Utilisateur : ", choices = choices_utilisateur))
                 ),
                 fluidRow(
                   column(12, selectInput("technicien", "Technicien : ", choices = choices_technicien))
                 ),
                 fluidRow(
                   column(12, selectInput("etat", "Etat : ", choices = choices_etat))
                 ),
                 fluidRow(
                   column(12, selectInput("urgence", "Urgence : ", choices = choices_urgence))
                 )
               ),
               mainPanel(
                 wellPanel(
                   h4("Résultats :"),
                 )
               )
             )
  )
 )
)
