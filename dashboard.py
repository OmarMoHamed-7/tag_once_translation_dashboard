import streamlit as st
import pandas as pd
import os # Import the os module to check for file existence

# --- Page Configuration ---
st.set_page_config(
    page_title="Translation Rules Dashboard",
    page_icon="📊",
    layout="wide",
)

# --- Helper Functions ---
# This function is cached to improve performance
@st.cache_data
def load_data(file_path):
    """Loads and preprocesses the CSV data. This function runs only when the input changes."""
    try:
        # keep_default_na=False is crucial to read empty cells as empty strings, not as a null value
        df = pd.read_csv(file_path, keep_default_na=False)

        # --- UPDATE: Remove the specified columns ---
        cols_to_drop = ['SB attributes', 'WY attributes']
        df = df.drop(columns=cols_to_drop, errors='ignore') # errors='ignore' prevents failure if columns don't exist

        # Identify the index of the 'WY event' column, which separates inputs from outputs
        try:
            wy_event_index = df.columns.get_loc('WY event')
        except KeyError:
            # This error is critical and stops the app if the column is missing
            st.error("CRITICAL ERROR: The required column 'WY event' was not found in the CSV file.")
            return pd.DataFrame(), [], []

        # Separate input and output columns based on the 'WY event' position
        input_cols = df.columns[:wy_event_index]
        output_cols = df.columns[wy_event_index:]

        # Clean up column names by removing leading/trailing whitespace
        df.columns = df.columns.str.strip()
        input_cols = [col.strip() for col in input_cols]
        output_cols = [col.strip() for col in output_cols]
        
        # --- UPDATE: Replace '~' with 'NOT' in all input columns ---
        for col in input_cols:
            if col in df.columns:
                # Ensure the column is treated as a string before replacing to avoid errors
                df[col] = df[col].astype(str).str.replace('~', 'NOT', regex=False)

        # --- FIX: Ensure all output columns are strings to prevent type mismatch issues ---
        for col in output_cols:
            if col in df.columns:
                df[col] = df[col].astype(str)

        return df, input_cols, output_cols
    except Exception as e:
        st.error(f"CRITICAL ERROR while loading data: {e}")
        return pd.DataFrame(), [], []

def display_merged_rules(df, input_cols, output_cols):
    """Groups rules by identical outputs and displays them in a merged format."""
    if df.empty:
        st.warning("No rules found for the selected criteria.")
        return

    # Group the DataFrame by all output columns. Rows with identical outputs will be in the same group.
    # dropna=False is important to treat empty/null values as a distinct group key.
    grouped = df.groupby(by=output_cols, dropna=False)

    st.subheader(f"Found {len(grouped)} Unique Output Rule(s)")
    
    rule_counter = 0
    # Iterate over each unique output group
    for output_values, group in grouped:
        rule_counter += 1
        st.markdown("---")
        st.markdown(f"#### Rule #{rule_counter}")

        # Create two columns for side-by-side display
        cols = st.columns([1, 1])

        # --- Display Merged Input Conditions (Left Column) ---
        with cols[0]:
            st.info("**SB Input Conditions (Source)**", icon="📥")
            # For each input column, find the unique values within the group and merge them
            for col in input_cols:
                # Get unique, non-empty values for the current input column in the group
                unique_vals = group[col].unique()
                cleaned_vals = [str(v) for v in unique_vals if pd.notna(v) and str(v).strip() != '' and str(v).strip() != 'NOT']
                
                # If there are any values to display for this input column, show them
                if cleaned_vals:
                    # Join multiple unique values with a separator
                    display_val = ' / '.join(sorted(cleaned_vals))
                    st.markdown(f"**{col}:** `{display_val}`")

        # --- Display Common Output (Right Column) ---
        with cols[1]:
            st.success("**WY Output (Destination)**", icon="📤")
            displayed_output = False
            # The output values are the keys of the group. We need to map them back to their column names.
            if not isinstance(output_values, tuple):
                output_values = (output_values,) # Ensure it's a tuple for zipping
            
            common_outputs = dict(zip(output_cols, output_values))

            for col, value in common_outputs.items():
                if pd.notna(value) and str(value).strip() != '':
                    st.markdown(f"**{col}:** `{value}`")
                    displayed_output = True
            
            if not displayed_output:
                st.markdown("_No specific output attributes for this rule._")


# --- Main Application ---
def main():
    """The main function that runs the Streamlit app."""
    # --- DRAW UI ELEMENTS FIRST ---
    st.sidebar.header("Filter Rules")
    st.title("📊 TagOnce Translation Rules")
    st.markdown("---")

    # --- Verify data file exists BEFORE trying to load it ---
    file_path = 'translation_rules.csv'
    if not os.path.exists(file_path):
        st.error(f"FATAL ERROR: The data file '{file_path}' was not found.")
        st.info(f"Please make sure the file is in the same folder as this script and has the correct name.")
        st.stop() # Halt execution if the file is missing

    # --- Load Data ---
    df, input_cols, output_cols = load_data(file_path)

    if df.empty:
        st.warning("Data could not be loaded or the file is empty. The application cannot proceed.")
        st.stop()

    # --- Primary Filter: WY Event ---
    wy_event_options = sorted(df['WY event'].unique().tolist())
    # --- UPDATE: Add 'All' as the first option for the filter ---
    options_with_all = ['All'] + wy_event_options
    
    selected_event = st.sidebar.selectbox(
        "1. Select a 'WY event':",
        options=options_with_all,
        index=0 # 'All' is the default because it's the first item (index 0)
    )
    
    # --- UPDATE: Filter dataframe based on the selection, handling the 'All' case ---
    if selected_event == 'All':
        # If 'All' is selected, use the entire dataframe
        filtered_df = df.copy()
    else:
        # Otherwise, filter by the specific event
        filtered_df = df[df['WY event'] == selected_event]

    # --- Secondary Filter: Output Attributes ---
    # Get all unique, non-blank values from the output columns of the already-filtered data
    all_output_values = filtered_df[output_cols].values.ravel()
    unique_attributes = pd.Series(all_output_values).dropna().unique()
    # Clean the list to remove empty strings and the event name itself
    cleaned_attributes = [attr for attr in unique_attributes if str(attr).strip() != '' and attr != selected_event]

    selected_attributes = st.sidebar.multiselect(
        "2. (Optional) Filter by WY Output Attributes:",
        options=sorted(cleaned_attributes),
        help="Select one or more attributes to show only the rules that contain them."
    )

    # Apply the secondary filter if any attributes are selected
    if selected_attributes:
        # --- "AND" LOGIC ---
        # This logic ensures that a row is kept only if ALL selected attributes are present in its output columns.
        mask = filtered_df.apply(
            lambda row: all(attr in row[output_cols].values for attr in selected_attributes),
            axis=1
        )
        final_df = filtered_df[mask]
    else:
        # If no attributes are selected, use the dataframe from the primary filter
        final_df = filtered_df


    # --- Display Results ---
    st.header(f"🔍 Visualizing Rules for: `{selected_event}`")
    display_merged_rules(final_df, input_cols, output_cols)


if __name__ == "__main__":
    main()

