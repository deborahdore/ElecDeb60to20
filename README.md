# ElecDeb60to20 Dataset

**OFFICIAL AND UPDATED REPOSITORY FOR THE ELECDEB60TO20 DATASET**

This dataset is a collection of televised debates of the US presidential campaign debates from **1960** to **2020** [[1](https://aclanthology.org/2023.emnlp-main.684)], [[2](https://aclanthology.org/P19-1463)], [[3](https://www.debates.org/voter-education/debate-transcripts/)].

----

The Dataset contains annotations for:
- Argument Components (Claim/Premises) and their boundaries
- Argument Components Relations (Support/Attack/Equivalent)
- Fallacies

Guidelines:
- [Argument Components](guidelines/component_guidelines.pdf)
- [Argument Components Relations](guidelines/relation_guidelines.pdf)
- [Fallacies](guidelines/fallacy_guidelines.pdf)

## Argumentative Component

The components are split into **Claims** and **Premises**.

### **Claims**

Being them the ultimate goal of an argument, in the context of political debates, claims can be a policy advocated by a
party or a candidate to be undertaken which needs to be justified in order to be accepted by the audience.

### **Premises**

Premises are assertions made by the debaters for supporting their claims (i.e., reasons
or justifications).

## Argumentative Relationship

The relationships are split into **Support** and **Attack**.

### **Support**

Links two components from a supporting argument component to a supported argument component.

### **Attack**

Holds when one argument component is in contradiction with another argument component


## Fallacy

> In the pragma-dialectical theory of argumentation [[Eemeren and
> Grootendorst, 1992](https://www.routledge.com/Argumentation-Communication-and-Fallacies-A-Pragma-dialectical-Perspective/van-Eemeren-Grootendorst/p/book/9780805810691); [Eemeren, 2010](https://doi.org/10.1075/aic.2)],
> fallacies are defined as
> “derailments of strategic manoeuvring”, meaning speech acts that
> violate the rules of a rational argumentative discussion for assumed
> persuasive gains.

Focus on **six** category of main fallacies and three of them are further divided into **sub-categories**:

1. **Ad Hominem**
    1. General
    2. Bias ad Hominem
    3. Tu quoque
    4. Name-calling, Labeling
2. **Appeal to Emotion**
    1. Appeal to Fear
    2. Appeal to Pity
    3. Loaded Language
    4. Flag Waving
3. **Appeal to Authority**
    1. Without evidence
    2. False authority
    3. Popular Opinion
4. **False Cause**
5. **Slippery Slope**
6. **Slogans**

